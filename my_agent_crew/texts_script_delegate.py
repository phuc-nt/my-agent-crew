"""Strings of a task handed to another agent from a script (`tools.delegate`,
`my_agent_crew/script/delegation.py`). Constants only, and nothing imported, as in
`texts_script`, whose strings these stand beside.
"""

# Closes what the model reads of `tool_script`, for an agent whose scripts may hand tasks on.
# The description is one agent's whatever turn reads it, so it says where this holds: a task
# the agent was itself handed is no turn of its own.
DELEGATE_DESCRIPTION = (
    "\nTrong lượt của chính bạn (không phải khi đang làm việc được agent khác giao), script còn "
    "giao việc được bằng `tools.delegate(task=..., agent=...)`; nhiều lời giao trong một "
    "`tools.batch` thì chạy song song, tối đa {most} việc cùng lúc."
)

# A task for an agent this one may not hand to. Known before any call of the batch is made,
# and the script ends there: the agents it may name are told, and what it named is not said
# again.
DELEGATE_WRONG_AGENT = (
    "`{name}` chưa chạy: `agent` phải là một trong: {allowed}; bỏ trống là giao cho chính "
    "mình. Sửa `agent` rồi chạy lại script."
)
