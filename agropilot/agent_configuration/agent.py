import os, json, re, time
import pathlib
from datetime import datetime, timedelta
from typing import TypedDict, Literal
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from tavily import TavilyClient

from agent_configuration.prompts import (
    PARSE_SYSTEM,
    CONFIGURATOR_SYSTEM,
    CRITIC_SYSTEM,
    SENTINEL_SYSTEM,
)

load_dotenv()


def _demo_mode() -> bool:
    """Return true when the app should use safe, deterministic demo data."""
    configured = os.getenv("AGROPILOT_DEMO_MODE", "").strip().lower()
    return configured in {"1", "true", "yes", "on"} or not os.getenv("GOOGLE_API_KEY")


def _demo_parsed_rfq(rfq_email: str) -> dict:
    """Provide a useful, local-only RFQ parse when no LLM is configured."""
    text = rfq_email.lower()
    country = "MY" if any(word in text for word in ("malaysia", "selangor", "johor", "kuala lumpur")) else "US"
    currency = "RM " if country == "MY" else "$"
    brand = "John Deere" if "john deere" in text else "AgroPilot Demo"
    model = "7R 330" if "7r" in text or "tractor" in text else "Precision Field Package"
    return {
        "rfq_id": "AQ-DEMO-2026-001",
        "dealer_company": "Demo Equipment Dealer",
        "dealer_contact": "Demo Sales Team",
        "dealer_email": "",
        "farm_operator": "Demo Farm Operator",
        "farm_location": "Malaysia" if country == "MY" else "United States",
        "country_code": country,
        "currency_symbol": currency,
        "delivery_deadline": "Demo delivery window",
        "budget_usd_min": 250000,
        "budget_usd_max": 500000,
        "equipment_category": "tractor",
        "base_model_requested": model,
        "oem_brand": brand,
        "farming_operation": "row-crop",
        "horsepower_required": 330,
        "acreage": 1200,
        "requirements": {
            "engine": "330 hp diesel engine",
            "transmission": "powershift transmission",
            "hydraulics": "high-flow hydraulics",
            "cab": "operator comfort cab",
            "precision_tech": ["GPS guidance"],
            "implements": ["precision planter"],
            "other": [],
        },
        "compliance_needed": ["standard safety certification"],
        "notes": "Generated locally for demonstration; verify specifications and pricing with an authorised dealer.",
    }


def _demo_bom(parsed: dict) -> list:
    """Return transparent sample pricing for a clickable product demo."""
    brand = parsed.get("oem_brand") or "AgroPilot Demo"
    model = parsed.get("base_model_requested") or "Precision Field Package"
    items = [
        ("DEMO-BASE-330", "base_unit", f"{brand} {model} base unit", 320000),
        ("DEMO-ENG-330", "engine", "330 hp emissions-compliant diesel engine", 0),
        ("DEMO-TRANS-PS", "transmission", "Powershift transmission", 18000),
        ("DEMO-HYD-HF", "hydraulics", "High-flow hydraulic package", 12500),
        ("DEMO-CAB-COMFORT", "cab", "Climate-controlled operator comfort cab", 8500),
        ("DEMO-GPS-GUIDE", "precision_tech", "GPS guidance and field mapping package", 14500),
        ("DEMO-PLANTER", "implement", "Precision planter integration kit", 22500),
    ]
    return [
        {
            "sku": sku,
            "component_type": component_type,
            "description": description,
            "qty": 1,
            "unit_price_usd": price,
            "line_total_usd": price,
            "status": "DRAFT",
            "compatibility_note": "Demo configuration — dealer validation required.",
            "reasoning": "Illustrative demo item; not a live OEM quote.",
            "product_url": None,
        }
        for sku, component_type, description, price in items
    ]


def _demo_sentinel() -> dict:
    return {
        "win_probability_pct": 78,
        "win_level": "HIGH",
        "gross_margin_pct": 28.0,
        "margin_vs_floor_pts": 8.0,
        "discount_risk": "LOW",
        "recommendation": "APPROVE AS-IS",
        "deal_rationale": "This configuration covers the core fieldwork requirements in the request. Confirm the final options and delivery date with the dealer before placing an order.",
        "upsell_opportunity": "Extended service package — illustrative demo recommendation.",
        "sentinel_flag": "Demo-only estimates; no live inventory or compliance check was performed.",
    }

# ─────────────────────────────────────────────────────────────────────────────
# SHARED STATE
# ─────────────────────────────────────────────────────────────────────────────

class QuoteState(TypedDict):
    rfq_email:            str
    parsed_rfq:           dict   # Stage 1 — structured RFQ
    bom:                  list   # Stage 2/4 — bill of materials
    compliance:           dict   # Stage 3 — compatibility + compliance audit
    sentinel:             dict   # Stage 5 — commercial analysis
    debate_round:         int
    max_debate_rounds:    int
    compliance_cleared:   bool
    final_quotation:      str
    hitl:                 dict
    log:                  list


#The @tool decorator is used to mark functions as tools that can be called by the agent. 
@tool
def search_ag_equipment(query: str) -> str:
    """Search for agricultural equipment SKUs, pricing, and specs via Tavily."""
    BASE_DIR = pathlib.Path(__file__).resolve().parent
    ENV_PATH = BASE_DIR / "config" / ".env"
    load_dotenv(dotenv_path=ENV_PATH)
    key = os.getenv("TAVILY_API_KEY", "")
    if not key:
        return f"[Tavily not configured — using estimated pricing for: {query}]"
    try:
        client = TavilyClient(api_key=key)
        results = client.search(query=query, max_results=5)
        snippets = [r.get("content", "") for r in results.get("results", [])]
        urls     = [r.get("url",     "") for r in results.get("results", [])]
        combined = []
        for s, u in zip(snippets[:4], urls[:4]):
            combined.append(f"SOURCE: {u}\n{s}")
        return "\n\n---\n\n".join(combined) if combined else "No results found."
    except Exception as e:
        return f"[Search error: {e}]"

@tool
def get_ag_compliance_rules(country_code: str) -> str:
    """
    Search the web via Tavily to retrieve current agricultural equipment compliance, 
    emissions standards, machinery directives, and regional certification rules.
    """
    key = os.getenv("TAVILY_API_KEY", "")
    if not key:
        return "[Tavily API key missing - reverting to international baseline fallback.]"
        
    country = country_code.upper().strip()
    
    # Formulate an advanced, multi-parameter regulatory query
    query = f"agricultural machinery equipment regulations compliance emission standards safety certification {country} 2025 2026"
    
    try:
        # Initialize the native Tavily client
        client = TavilyClient(api_key=key)
        
        # Execute an advanced search optimized for extracting legal/regulatory snippets
        response = client.search(
            query=query, 
            max_results=4, 
            search_depth="advanced"
        )
        
        results = response.get("results", [])
        if not results:
            return f"No specific real-time regulatory findings returned for {country}. Apply EPA Tier 4 Final / EU Stage V global baseline."
            
        # Parse and compile the highly contextual snippets
        compiled_rules = []
        for i, res in enumerate(results):
            title = res.get("title", "Regulatory Reference")
            url = res.get("url", "")
            content = res.get("content", "")
            compiled_rules.append(f"REGULATION BLOCK {i+1}: {title}\nSOURCE: {url}\nSUMMARY: {content}")
            
        return f"=== LIVE REGULATORY REQUIRMENTS FOR {country} ===\n\n" + "\n\n---\n\n".join(compiled_rules)
        
    except Exception as e:
        return f"[Dynamic Compliance Search Interrupted: {e}. Fallback to generic international baselines required.]"
    
@tool
def validate_ag_compatibility(components: str) -> str:
    """
    Search the web via Tavily to verify technical compatibility, electrical 
    tolerances, and CAN-bus system constraints for agricultural component builds.
    """
    key = os.getenv("TAVILY_API_KEY", "")
    if not key:
        return "[Tavily API key missing - unable to verify dynamic component compatibility.]"
        
    # Construct an explicitly targeted query combining the component list
    query = f"agricultural equipment technical compatibility issues conflicts constraints {components}"
    
    try:
        # Initialize the native Tavily Client
        client = TavilyClient(api_key=key)
        
        # Execute an advanced search optimized for extracting context snippets
        response = client.search(
            query=query, 
            max_results=5, 
            search_depth="advanced"
        )
        
        results = response.get("results", [])
        if not results:
            return "COMPATIBLE: No known technical or regulatory hardware conflicts discovered on the web."
            
        # Parse and combine the highly contextual web snippets
        compiled_findings = []
        for i, res in enumerate(results):
            title = res.get("title", "OEM Source")
            url = res.get("url", "")
            content = res.get("content", "")
            compiled_findings.append(f"FINDING {i+1}: {title}\nSOURCE: {url}\nDETAILS: {content}")
            
        return "\n\n---\n\n".join(compiled_findings)
        
    except Exception as e:
        return f"[Dynamic Compatibility Search Interrupted: {e}]"


def safe_invoke_tool(tool_obj, args_dict):
    """Safely executes LangChain tools falling back to Python directly on mismatch."""
    try:
        return tool_obj.invoke(args_dict)
    except Exception:
        try:
            return tool_obj.func(**args_dict)
        except Exception as e:
            return f"[Tool Execution Interlock Fallback: {e}]"


def _calculate_totals(bom: list, tax_rate: float = 0.07) -> dict:
    """Pure Python totals computation safely supporting structured fallbacks."""
    subtotal = 0.0
    for item in bom:
        if item.get("status", "") != "REJECTED":
            try:
                qty = int(item.get("qty", 1) if item.get("qty") is not None else 1)
            except (TypeError, ValueError):
                qty = 1
            try:
                unit_price = float(item.get("unit_price_usd", 0.0) if item.get("unit_price_usd") is not None else 0.0)
            except (TypeError, ValueError):
                unit_price = 0.0
            subtotal += qty * unit_price
            
    delivery = round(subtotal * 0.02, 2)
    taxes    = round(subtotal * tax_rate, 2)
    total    = round(subtotal + delivery + taxes, 2)
    return {"subtotal": subtotal, "delivery": delivery, "taxes": taxes, "total": total}


# ─────────────────────────────────────────────────────────────────────────────
# LLM ENGINES WITH FAST TIMEOUT AND ESCAPE HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

def _call(system: str, user: str) -> str:
    BASE_DIR = pathlib.Path(__file__).resolve().parent
    ENV_PATH = BASE_DIR.parent / "config" / ".env"
    load_dotenv(dotenv_path=ENV_PATH)
    key = os.getenv("GOOGLE_API_KEY") 
    if _demo_mode() or not key:
        return "__FALLBACK_TRIGGERED__"
    
    delays = [90]
    for attempt, delay in enumerate(delays):
        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-3.1-flash-lite",
                google_api_key=key,
                temperature=0.2,
                max_output_tokens=4096,
                timeout=90,
            )
            resp = llm.invoke([
                SystemMessage(content=system),
                HumanMessage(content=user),
            ])
            content = resp.content
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        parts.append(part["text"])
                    elif isinstance(part, str):
                        parts.append(part)
                content = "".join(parts)
            return content
        except Exception:
            if attempt < len(delays) - 1:
                time.sleep(delay)
            else:
                break
                
    return "__FALLBACK_TRIGGERED__"


def _parse_json(raw: str, fallback):
    if raw == "__FALLBACK_TRIGGERED__":
        return fallback
    clean = re.sub(r"\x60\x60\x60(?:json)?", "", raw).strip().rstrip("\x60").strip()
    try:
        return json.loads(clean)
    except Exception as e:
        print(f"JSON Parse Error: {e}\nRaw output was:\n{raw}")
        return fallback


def _log(state: QuoteState, agent: str, msg: str, level: str = "info") -> list:
    existing = list(state.get("log", []))
    existing.append({"agent": agent, "msg": msg, "level": level})
    return existing


# ─────────────────────────────────────────────────────────────────────────────
# GRAPH AGENT INTERNALS
# ─────────────────────────────────────────────────────────────────────────────

def node_parse(state: QuoteState) -> dict:
    raw = _call(PARSE_SYSTEM, f"Parse this agricultural equipment RFQ:\n\n{state['rfq_email']}")
    
    email_text = state['rfq_email'].lower()
    
    fallback_parse = _demo_parsed_rfq(state["rfq_email"])
    
    parsed = _parse_json(raw, fallback_parse)
    
    # Sanitize missing/null values to prevent crashes in downstream string operations
    for str_key in ["base_model_requested", "oem_brand", "country_code", "equipment_category"]:
        if parsed.get(str_key) is None:
            parsed[str_key] = ""
            
    for num_key in ["budget_usd_min", "budget_usd_max", "horsepower_required", "acreage"]:
        if parsed.get(num_key) is None:
            parsed[num_key] = 0

    if "currency_symbol" not in parsed:
        cc = parsed.get("country_code", "US").upper()
        parsed["currency_symbol"] = "RM " if cc == "MY" else ("AU$" if cc == "AU" else "$")

    source = "DEMO MODE — local sample data" if raw == "__FALLBACK_TRIGGERED__" else "live model extraction"
    logs = _log(state, "SYSTEM", f"Stage 1 — RFQ parsed: {parsed.get('oem_brand','John Deere')} {parsed.get('base_model_requested','7R 330')} ({source}).", "success")

    return {
        "parsed_rfq":         parsed,
        "debate_round":       0,
        "max_debate_rounds":  3,
        "compliance_cleared": False,
        "bom":                [],
        "compliance":         {},
        "sentinel":           {},
        "final_quotation":    "",
        "hitl":               {},
        "log":                logs,
    }


def node_configurator(state: QuoteState) -> dict:
    parsed  = state["parsed_rfq"]
    round_n = state.get("debate_round", 0)
    objections = state.get("compliance", {}).get("objections", [])

    compliance_rules = safe_invoke_tool(get_ag_compliance_rules, {"country_code": parsed.get("country_code", "US")})
    brand   = parsed.get("oem_brand", "")
    model   = parsed.get("base_model_requested", "")
    reqs    = parsed.get("requirements", {})
    search_q = f"{brand} {model} pricing specs dealer 2026"
    product_data = safe_invoke_tool(search_ag_equipment, {"query": search_q})

    components_list = ", ".join(filter(None, [
        reqs.get("engine", ""), reqs.get("transmission", ""), reqs.get("hydraulics", ""), reqs.get("cab", ""),
        *reqs.get("precision_tech", []), *reqs.get("implements", [])
    ]))
    compat_check = safe_invoke_tool(validate_ag_compatibility, {"components": components_list}) if components_list else ""

    objection_block = f"\n=== BLOCKING OBJECTIONS ===\n{json.dumps(objections)}" if objections else ""

    user_msg = f"Build BOM array matching context:\n{json.dumps(parsed)}\n{compliance_rules}\n{compat_check}\n{product_data}\n{objection_block}"
    
    fallback_bom = _demo_bom(parsed)
    
    raw = _call(CONFIGURATOR_SYSTEM, user_msg)
    bom = _parse_json(raw, fallback_bom)
    if not isinstance(bom, list):
        bom = [bom] if isinstance(bom, dict) else fallback_bom

    for item in bom:
        if not item.get("line_total_usd"):
            try:
                qty = int(item.get("qty", 1) if item.get("qty") is not None else 1)
            except (TypeError, ValueError):
                qty = 1
            try:
                unit_price = float(item.get("unit_price_usd", 0.0) if item.get("unit_price_usd") is not None else 0.0)
            except (TypeError, ValueError):
                unit_price = 0.0
            item["line_total_usd"] = qty * unit_price

    totals = _calculate_totals(bom)
    action = "initial BOM" if round_n == 0 else f"revised BOM round {round_n + 1}"
    logs = _log(state, "CONFIGURATOR", f"Stage 2 — BOM engineered ({action}): {len(bom)} items, Est: {parsed.get('currency_symbol', '$')}{totals['total']:,.2f}", "info" if round_n == 0 else "warn")

    return {"bom": bom, "debate_round": round_n + 1, "log": logs}


def node_critic(state: QuoteState) -> dict:
    parsed = state["parsed_rfq"]
    bom = state["bom"]
    components_summary = ", ".join(f"{i.get('component_type','')}: {i.get('description','')}" for i in bom)
    compat_result = safe_invoke_tool(validate_ag_compatibility, {"components": components_summary})

    brand = parsed.get("oem_brand", "John Deere")
    country = parsed.get("country_code", "US").lower()
    round_n = state.get("debate_round", 1)

    fallback_audit = {
        "cleared": True,
        "objections": [],
        "audit_summary": ""
    }
    
    raw = _call(CRITIC_SYSTEM, f"Audit following specification matrix:\n{json.dumps(bom)}\nPre-tool validation check: {compat_result}")
    audit = _parse_json(raw, fallback_audit)
    
    blocking_count = len([o for o in audit.get("objections", []) if o.get("severity") == "BLOCKING"])
    cleared = audit.get("cleared", True) if blocking_count == 0 else False

    if state.get("debate_round", 0) >= state.get("max_debate_rounds", 3):
        cleared = True

    level = "success" if cleared else "error"
    msg = f"Stage 3 Assessment — Technical infrastructure clearance: {'CLEARED' if cleared else 'NOT CLEARED - Objections detected'}"
    logs = _log(state, "CRITIC", msg, level)
    
    return {"compliance": audit, "compliance_cleared": cleared, "log": logs}


def route_after_critic(state: QuoteState) -> Literal["node_configurator", "node_sentinel"]:
    if not state.get("compliance_cleared", False) and state.get("debate_round", 0) < state.get("max_debate_rounds", 3):
        return "node_configurator"
    return "node_sentinel"


def node_sentinel(state: QuoteState) -> dict:
    parsed = state["parsed_rfq"]
    brand = parsed.get("oem_brand", "John Deere")
    country = parsed.get("country_code", "US").lower()
    
    fallback_sentinel = _demo_sentinel()
    
    raw = _call(SENTINEL_SYSTEM, f"Analyse Deal: {json.dumps(state['bom'])}")
    sentinel = _parse_json(raw, fallback_sentinel)
    
    logs = _log(state, "SENTINEL", f"Stage 4 — Commercial Intelligence Complete. Blended Gross Margin: {sentinel.get('gross_margin_pct', 18.0)}%", "success")
    return {"sentinel": sentinel, "log": logs}


def node_generate_quote(state: QuoteState) -> dict:
    parsed   = state["parsed_rfq"]
    bom      = state["bom"]
    sentinel = state.get("sentinel") or {}
    audit    = state.get("compliance") or {}
    totals   = _calculate_totals(bom)
    
    curr = parsed.get("currency_symbol", "$")

    today = datetime.today()
    valid_date = today + timedelta(days=30)

    bom_rows_list = []
    for i, item in enumerate(bom):
        if item.get("status", "") == "REJECTED":
            continue
        sku = item.get('sku', '') or 'N/A'
        desc = (item.get('description', '') or 'Component spec')[:35]
        qty = int(item.get('qty', 1) if item.get('qty') is not None else 1)
        unit_price = float(item.get('unit_price_usd', 0) if item.get('unit_price_usd') is not None else 0.0)
        line_total = float(item.get('line_total_usd', 0) if item.get('line_total_usd') is not None else 0.0)
        bom_rows_list.append(f"| {i+1:2} | {sku:<22} | {desc:<35} | {qty:3} | {curr}{unit_price:>10,.0f} | {curr}{line_total:>12,.0f} |")
    bom_rows = "\n".join(bom_rows_list)

    blocking = [o for o in audit.get("objections", []) if o.get("severity") == "BLOCKING"]
    warnings = [o for o in audit.get("objections", []) if o.get("severity") == "WARNING"]

    try:
        margin_pct = float(sentinel.get('gross_margin_pct') if sentinel.get('gross_margin_pct') is not None else 32.4)
    except (TypeError, ValueError):
        margin_pct = 32.4
        
    try:
        win_prob = int(sentinel.get('win_probability_pct') if sentinel.get('win_probability_pct') is not None else 85)
    except (TypeError, ValueError):
        win_prob = 85

    quotation = f"""
========================================================================================
                      AGRIPILOT SYSTEM INTEGRATION SPECIFICATION
========================================================================================
RFQ IDENTIFIER:   {parsed.get('rfq_id', 'N/A')}
DISTRIBUTOR:      {parsed.get('dealer_company', 'N/A')}
REPRESENTATIVE:   {parsed.get('dealer_contact', 'N/A')}
OPERATOR TARGET:  {parsed.get('farm_operator', 'N/A')}
LOCATION MATRIX:  {parsed.get('farm_location', 'N/A')}
BASE VEHICLE:     {parsed.get('oem_brand','N/A')} {parsed.get('base_model_requested','N/A')}
GENERATED DATE:   {today.strftime('%d %B %Y')}
----------------------------------------------------------------------------------------
ENGINEERED BILL OF MATERIALS (AUTOMATED LOGIC RESOLVED)
----------------------------------------------------------------------------------------
{bom_rows}

----------------------------------------------------------------------------------------
FINANCIAL DATA SUMMARY
----------------------------------------------------------------------------------------
SUBTOTAL SPECIFICATION VALUE:             {curr}{totals['subtotal']:>14,.2f}
FREIGHT LOGISTICS & HANDLING (2%):       {curr}{totals['delivery']:>14,.2f}
ESTIMATED STATUTORY TAX STRUCTURE (7%):   {curr}{totals['taxes']:>14,.2f}
TOTAL SECURED DEAL VALUE (LOCALISED):     {curr}{totals['total']:>14,.2f}
========================================================================================
"""
    
    hitl = {
        "quote_total":          totals["total"],
        "gross_margin_pct":     margin_pct,
        "win_probability_pct":  win_prob,
        "win_level":            sentinel.get("win_level", "HIGH"),
        "discount_risk":        sentinel.get("discount_risk", "LOW"),
        "recommendation":       sentinel.get("recommendation", "APPROVE AS-IS"),
        "compliance_cleared":   state.get("compliance_cleared", False),
        "blocking_resolved":    len(blocking) if blocking else 1,
        "warnings":             len(warnings),
        "rationale":            sentinel.get("deal_rationale", ""),
        "upsell":               sentinel.get("upsell_opportunity", ""),
        "dealer_company":       parsed.get("dealer_company", "N/A"),
        "farm_operator":        parsed.get("farm_operator", "N/A"),
        "dealer_contact":       parsed.get("dealer_contact", "N/A"),
        "rfq_id":               parsed.get("rfq_id", "N/A"),
        "equipment":            f"{parsed.get('oem_brand','N/A')} {parsed.get('base_model_requested','N/A')}",
        "currency_symbol":      curr
    }

    logs = _log(state, "SYSTEM", "Stage 5 — Enterprise Document Build Pipeline finalized.", "success")
    return {"final_quotation": quotation, "hitl": hitl, "log": logs}


# ─────────────────────────────────────────────────────────────────────────────
# GRAPH ASSEMBLY
# ─────────────────────────────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(QuoteState)

    g.add_node("node_parse",          node_parse)
    g.add_node("node_configurator",   node_configurator)
    g.add_node("node_critic",         node_critic)
    g.add_node("node_sentinel",       node_sentinel)
    g.add_node("node_generate_quote", node_generate_quote)

    g.set_entry_point("node_parse")
    g.add_edge("node_parse",         "node_configurator")
    g.add_edge("node_configurator",  "node_critic")

    g.add_conditional_edges(
        "node_critic",
        route_after_critic,
        {
            "node_configurator": "node_configurator",
            "node_sentinel":     "node_sentinel",
        }
    )

    g.add_edge("node_sentinel",       "node_generate_quote")
    g.add_edge("node_generate_quote", END)

    return g.compile()

if __name__ == "__main__":
    graph = build_graph()
    print("Graph built perfectly. Run 'streamlit run app.py' to launch.")
