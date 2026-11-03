# LLM prompt templates (paper Appendix A)

Used by `contextxr.methods.llm`. Text is byte-identical to the paper runs. The system prompts were checked against the SHA-256 recorded in the paper's result files.

| file | role |
|---|---|
| `system_zero_shot.txt` | system prompt, zero-shot LLM (initial and next facet suggestion) |
| `system_few_shot.txt` | system prompt, few-shot LLM |
| `user_zero_shot.txt` | user prompt, zero-shot (`{details_block}` is empty for initial facet suggestion) |
| `user_few_shot.txt` | user prompt, few-shot, with the transfer condition and historical examples |
| `support_example.txt` | one historical example in `{support_block}` (examples are separated by a blank line) |
| `next_facet_history.txt` | `{details_block}` body for next facet suggestion (the already placed facets) |
| `placed_facet_line.txt` | one placed facet in `next_facet_history.txt` |

`{catalog_text}` is one JSON line per facet: `{"facet_id", "app", "name", "description", "is_entry_facet", "linked_facets", "capabilities"}`, numbered `1.`, `2.`, … in facet-DB order.
