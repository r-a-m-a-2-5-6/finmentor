from __future__ import annotations

import json
from typing import Optional

from app.agents.calculator.tools import TOOLS
from app.agents.shared.llm import get_llm
from app.agents.shared.types import CalculationResult, PlanTask


class CalculatorAgent:
    """
    Deterministic Calculator Agent (LangChain v1 compatible).
    Executes tools directly — no LLM agent layer.
    """

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.0)  # kept for consistency

    def run(self, tasks: list[PlanTask]) -> list[CalculationResult]:
        if not tasks:
            return []

        results: list[CalculationResult] = []

        for task in tasks:
            tool_name = task.tool
            params = task.params

            # 🔍 Find tool
            tool = next((t for t in TOOLS if t.name == tool_name), None)

            if not tool:
                results.append(
                    CalculationResult(
                        tool=tool_name,
                        result={"error": f"Tool '{tool_name}' not found"},
                        success=False,
                    )
                )
                continue

            try:
                # ⚡ Execute tool
                output = tool.invoke(params)

                # Normalize output
                if isinstance(output, str):
                    try:
                        output = json.loads(output)
                    except Exception:
                        output = {"raw": output}

                results.append(
                    CalculationResult(
                        tool=tool_name,
                        result=output,
                        success=output.get("status") == "success",
                    )
                )

            except Exception as e:
                results.append(
                    CalculationResult(
                        tool=tool_name,
                        result={"error": str(e)},
                        success=False,
                    )
                )

        return results