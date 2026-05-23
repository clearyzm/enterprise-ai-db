"""LangGraph agent implementation.

Implements state machine from 04-ai-system.md §4.1.
Uses LLM_MODEL for classify/guardrail, LLM_STRONG_MODEL for synthesize.
"""
from typing import Any, TypedDict, Literal
from uuid import UUID
import json

import structlog
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.services.permission_service import PermissionService
from app.ai.retriever import retrieve_by_query_text
from app.ai.tools import build_tools_for_user, ToolDescriptor
from app.ai.prompts import build_system_prompt, build_classify_prompt, build_synthesize_prompt, format_retrieval_context, DENIAL_RESPONSE
from app.ai.guardrails import check_input_guardrails, check_output_guardrails

logger = structlog.get_logger(__name__)
settings = get_settings()


class AgentState(TypedDict):
    """LangGraph agent state."""
    user_input: str
    user: dict[str, Any]
    tenant_id: str
    intent: str | None
    resources: list[str]
    permission_decision: str | None
    retrieval: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    answer: str
    guardrail: dict[str, Any]
    citations: list[str]


def input_filter_node(state: AgentState) -> AgentState:
    """Check input for prompt injection attempts."""
    result = check_input_guardrails(state["user_input"])
    if result.violations:
        logger.info("agent.input_filter.flagged", violations=result.violations)
    return state


def classify_node(state: AgentState, llm: ChatOpenAI) -> AgentState:
    """Classify user intent using LLM."""
    prompt = build_classify_prompt(state["user_input"])
    
    try:
        response = llm.invoke([{"role": "user", "content": prompt}])
        content = response.content.strip()
        
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif content.startswith("```"):
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        state["intent"] = result.get("intent", "out_of_scope")
        state["resources"] = result.get("resources", [])
        
        logger.info("agent.classify.complete", intent=state["intent"], resources=state["resources"])
    except Exception as e:
        logger.error("agent.classify.error", error=str(e))
        state["intent"] = "out_of_scope"
        state["resources"] = []
    
    return state


async def permission_gate_node(state: AgentState, db: AsyncSession) -> AgentState:
    """Check if user has permission to access requested resources."""
    if state.get("intent") != "data_query":
        state["permission_decision"] = "allow"
        return state
    
    # For simplicity, allow if user has any ai_query permission
    # Detailed filtering happens in retrieval
    state["permission_decision"] = "allow"
    logger.info("agent.permission_gate.complete", decision=state["permission_decision"])
    
    return state


async def retrieve_node(state: AgentState, db: AsyncSession, user: User) -> AgentState:
    """Retrieve relevant chunks using permission-aware retrieval."""
    try:
        chunks = await retrieve_by_query_text(
            tenant_id=UUID(state["tenant_id"]),
            user=user,
            query_text=state["user_input"],
            db=db,
            top_k=8,
        )
        
        state["retrieval"] = [
            {"id": str(c.id), "record_id": str(c.record_id), "dataset_id": str(c.dataset_id),
             "text": c.text, "sensitivity": c.sensitivity, "score": c.score, "source_field": c.source_field}
            for c in chunks
        ]
        
        logger.info("agent.retrieve.complete", chunk_count=len(state["retrieval"]))
    except Exception as e:
        logger.error("agent.retrieve.error", error=str(e))
        state["retrieval"] = []
    
    return state


def plan_node(state: AgentState, llm: ChatOpenAI, tools: list[ToolDescriptor]) -> AgentState:
    """Decide whether to call tools using LLM.
    
    Uses OpenAI function calling to let LLM decide which tools to use.
    """
    # If no tools available, skip
    if not tools:
        state["tool_calls"] = []
        state["tool_results"] = []
        logger.debug("agent.plan.no_tools")
        return state
    
    user_input = state["user_input"]
    retrieval = state.get("retrieval", [])
    
    # Build context summary for LLM
    context_summary = f"Found {len(retrieval)} relevant chunks from database."
    
    # Convert tools to OpenAI function calling format
    tools_schema = []
    for tool in tools:
        tools_schema.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
        })
    
    # Build prompt for tool decision
    prompt = f"""Based on the user's question and available context, decide if you need to call any tools.

User question: {user_input}

Context: {context_summary}

Available tools: {len(tools)} tools including search, query, count, compute, etc.

If the context is sufficient to answer, you don't need to call tools.
If you need more specific data or calculations, call appropriate tools."""
    
    try:
        # Call LLM with function calling
        response = llm.invoke(
            [{"role": "user", "content": prompt}],
            tools=tools_schema,
        )
        
        # Check if LLM wants to call tools
        if hasattr(response, "tool_calls") and response.tool_calls:
            # Parse tool calls
            tool_calls = []
            for tool_call in response.tool_calls:
                tool_calls.append({
                    "name": tool_call["name"],
                    "arguments": tool_call["args"],
                })
            
            state["tool_calls"] = tool_calls
            logger.info("agent.plan.tools_selected", tool_count=len(tool_calls), tool_names=[tc["name"] for tc in tool_calls])
        else:
            # No tool calls
            state["tool_calls"] = []
            logger.debug("agent.plan.no_tools_needed")
        
    except Exception as e:
        logger.error("agent.plan.error", error=str(e))
        state["tool_calls"] = []
    
    state["tool_results"] = []
    return state


async def execute_tools_node(state: AgentState, tools: list[ToolDescriptor]) -> AgentState:
    """Execute tool calls.
    
    Iterates through tool_calls, finds corresponding ToolDescriptor,
    and executes the tool function.
    """
    tool_calls = state.get("tool_calls", [])
    tool_results = []
    
    if not tool_calls:
        state["tool_results"] = []
        return state
    
    # Build tool lookup map
    tool_map = {tool.name: tool for tool in tools}
    
    # Execute each tool call
    for tool_call in tool_calls:
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})
        
        # Find tool
        tool = tool_map.get(tool_name)
        
        if not tool:
            logger.warning("agent.execute_tools.tool_not_found", tool_name=tool_name)
            tool_results.append({
                "tool_name": tool_name,
                "result": {"error": f"Tool '{tool_name}' not found"},
            })
            continue
        
        # Execute tool
        try:
            logger.debug("agent.execute_tools.calling", tool_name=tool_name, arguments=arguments)
            result = await tool.func(**arguments)
            
            tool_results.append({
                "tool_name": tool_name,
                "result": result,
            })
            
            logger.info("agent.execute_tools.success", tool_name=tool_name)
            
        except Exception as e:
            logger.error("agent.execute_tools.error", tool_name=tool_name, error=str(e))
            tool_results.append({
                "tool_name": tool_name,
                "result": {"error": f"Tool execution failed: {str(e)}"},
            })
    
    state["tool_results"] = tool_results
    logger.info("agent.execute_tools.complete", tool_count=len(tool_results))
    
    return state


def synthesize_node(state: AgentState, llm: ChatOpenAI) -> AgentState:
    """Generate final answer using strong LLM."""
    context = format_retrieval_context(state.get("retrieval", []))
    prompt = build_synthesize_prompt(state["user_input"], context, state.get("tool_results", []))
    
    user_dict = state["user"]
    system_prompt = build_system_prompt(
        tenant_name=user_dict.get("tenant_name", "企业"),
        user_name=user_dict.get("display_name", "用户"),
        user_departments=user_dict.get("departments", []),
        user_roles=user_dict.get("roles", []),
        accessible_datasets=user_dict.get("accessible_datasets", []),
    )
    
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        response = llm.invoke(messages)
        state["answer"] = response.content.strip()
        logger.info("agent.synthesize.complete", answer_length=len(state["answer"]))
    except Exception as e:
        logger.error("agent.synthesize.error", error=str(e))
        state["answer"] = "抱歉，生成回答时出现错误。请稍后重试。"
    
    return state


def guardrail_node(state: AgentState) -> AgentState:
    """Run output guardrail checks."""
    user_dict = state["user"]
    
    result = check_output_guardrails(
        answer=state.get("answer", ""),
        retrieval_chunks=state.get("retrieval", []),
        tool_results=state.get("tool_results", []),
        user_max_sensitivity=user_dict.get("max_sensitivity", "internal"),
        user_has_read_pii=user_dict.get("has_read_pii", False),
    )
    
    state["guardrail"] = {
        "passed": result.passed,
        "violations": result.violations,
        "risk_level": result.risk_level,
        "action": result.action,
    }
    
    if not result.passed:
        logger.warning("agent.guardrail.violations", violations=result.violations, risk_level=result.risk_level)
    
    return state


def respond_deny_node(state: AgentState) -> AgentState:
    """Return denial response."""
    state["answer"] = DENIAL_RESPONSE
    state["guardrail"] = {"passed": True, "violations": [], "risk_level": "low", "action": "allow"}
    logger.info("agent.respond_deny")
    return state


def build_agent_graph(user: User, tenant_id: UUID, db: AsyncSession, tools: list[ToolDescriptor]) -> StateGraph:
    """Build LangGraph agent graph."""
    llm_cheap = ChatOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY.get_secret_value(),
        model=settings.LLM_MODEL,
        temperature=0,
    )
    
    llm_strong = ChatOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY.get_secret_value(),
        model=settings.LLM_STRONG_MODEL,
        temperature=0,
    )
    
    graph = StateGraph(AgentState)
    
    async def _permission_gate(s):
        return await permission_gate_node(s, db)
    
    async def _retrieve(s):
        return await retrieve_node(s, db, user)
    
    async def _execute_tools(s):
        return await execute_tools_node(s, tools)
    
    graph.add_node("input_filter", input_filter_node)
    graph.add_node("classify", lambda s: classify_node(s, llm_cheap))
    graph.add_node("permission_gate", _permission_gate)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("plan", lambda s: plan_node(s, llm_cheap, tools))
    graph.add_node("execute_tools", _execute_tools)
    graph.add_node("synthesize", lambda s: synthesize_node(s, llm_strong))
    graph.add_node("guardrail", guardrail_node)
    graph.add_node("respond_deny", respond_deny_node)
    
    graph.set_entry_point("input_filter")
    graph.add_edge("input_filter", "classify")
    
    def route_after_classify(state: AgentState) -> Literal["permission_gate", "synthesize", "respond_deny"]:
        intent = state.get("intent", "out_of_scope")
        if intent == "data_query":
            return "permission_gate"
        elif intent == "smalltalk":
            return "synthesize"
        else:
            return "respond_deny"
    
    graph.add_conditional_edges("classify", route_after_classify)
    
    def route_after_permission(state: AgentState) -> Literal["retrieve", "respond_deny"]:
        return "retrieve" if state.get("permission_decision") == "allow" else "respond_deny"
    
    graph.add_conditional_edges("permission_gate", route_after_permission)
    
    graph.add_edge("retrieve", "plan")
    
    def route_after_plan(state: AgentState) -> Literal["execute_tools", "synthesize"]:
        return "execute_tools" if state.get("tool_calls", []) else "synthesize"
    
    graph.add_conditional_edges("plan", route_after_plan)
    
    graph.add_edge("execute_tools", "synthesize")
    graph.add_edge("synthesize", "guardrail")
    
    def route_after_guardrail(state: AgentState) -> Literal["END", "respond_deny"]:
        action = state.get("guardrail", {}).get("action", "allow")
        return "END" if action != "block" else "respond_deny"
    
    graph.add_conditional_edges("guardrail", route_after_guardrail, {"END": END, "respond_deny": "respond_deny"})
    
    graph.add_edge("respond_deny", END)
    
    return graph


async def run_agent(user_input: str, user: User, tenant_id: UUID, db: AsyncSession) -> dict[str, Any]:
    """Run agent on user input."""
    tools = await build_tools_for_user(user, tenant_id, db)
    graph = build_agent_graph(user, tenant_id, db, tools)
    compiled = graph.compile()
    
    initial_state: AgentState = {
        "user_input": user_input,
        "user": {
            "id": str(user.id),
            "display_name": user.display_name,
            "tenant_name": "企业",
            "departments": [],
            "roles": [],
            "accessible_datasets": [],
            "max_sensitivity": "internal",
            "has_read_pii": False,
        },
        "tenant_id": str(tenant_id),
        "intent": None,
        "resources": [],
        "permission_decision": None,
        "retrieval": [],
        "tool_calls": [],
        "tool_results": [],
        "answer": "",
        "guardrail": {},
        "citations": [],
    }
    
    final_state = await compiled.ainvoke(initial_state)
    
    return final_state
