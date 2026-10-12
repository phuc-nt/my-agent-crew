"""Strings of what a script keeps from one run to the next (`store` and `load`,
`my_agent_crew/script/kept.py`). Constants only, and nothing imported: the child process that
runs a script loads this module with the site packages switched off, as it does `texts_script`.
"""

# Mistakes a script can catch and carry on from. The write that met one was not taken.
STORE_BAD_KEY = "khoá của store/load phải là một chuỗi không rỗng, dài tối đa {most} ký tự."
STORE_NOT_JSON = (
    "store chỉ giữ được dữ liệu JSON: chuỗi, số, True/False, None, list, và dict có khoá là "
    "chuỗi (khoá là số thì đổi sang str trước)."
)
STORE_VALUE_TOO_LONG = (
    "giá trị viết thành JSON dài {size} ký tự, quá {most} ký tự cho một khoá: lưu gọn hơn "
    "hoặc chia ra nhiều khoá."
)
STORE_FULL = (
    "kho đầy: ghi thêm thì kho chứa {size} ký tự (khoá và giá trị), quá {most}. Xoá bớt bằng "
    "store(khoá, None) hoặc lưu gọn hơn."
)
# A script that belongs to no conversation and no job has nowhere to keep anything.
STORE_NOWHERE = (
    "không có chỗ để giữ: script này không chạy trong cuộc trò chuyện hay job nào, nên store "
    "và load không dùng được ở đây."
)
# Ends the answer of a script that ran to its end and still kept nothing: while it ran,
# another run filled the same store, and what this one wrote no longer fits beside it.
STORE_NOT_KEPT = (
    "Script chạy xong nhưng KHÔNG giữ được gì bằng store: trong lúc nó chạy, một lần chạy khác "
    "đã ghi vào cùng kho và không còn đủ chỗ (tối đa {most} ký tự). Chạy lại script."
)
# Ends the answer of a script that ran to its end for an agent that was removed meanwhile, or
# before it began in a turn that outlived the agent: what it stored has no agent to belong to.
# One that only loaded after the removal ends on it too, having been answered with nothing.
STORE_AGENT_GONE = (
    "Script chạy xong nhưng KHÔNG giữ được gì bằng store: agent chạy script này đã bị gỡ khỏi "
    "đội, nên những gì nó lưu không còn thuộc về ai."
)
