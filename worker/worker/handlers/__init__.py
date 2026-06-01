"""
Handler registry — maps job type strings to async handler functions.
Each handler receives a JobContext and returns the final payload dict.
"""
from worker.handlers.echo import handle as echo_handle
from worker.handlers.planner import handle as planner_handle
from worker.handlers.research import handle as research_handle

HANDLERS: dict[str, object] = {
    "echo": echo_handle,
    "generate_plan": planner_handle,
    "research_subtopic": research_handle,
}
