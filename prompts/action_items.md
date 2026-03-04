You are extracting action items from a raw transcript of a research project meeting.

Your job is to carefully identify every task, next step, or commitment that was discussed — whether explicitly stated or implicitly agreed upon.

Rules:
- For EACH action item, be specific and detailed: include the exact method, dataset, parameter, metric, or approach discussed. Do NOT summarize vaguely (e.g., "run more experiments"). Instead, spell out what the experiment is, what data to use, and what to measure.
- Do NOT attribute action items to specific people. Just list what needs to be done for the project.
- Include decisions that imply work (e.g., "let's use log scale" → regenerate the plot with log-scale x-axis)
- Include deprioritized items too, but mark them (e.g., "low priority" or "not blocking")
- Output format: a single Obsidian callout block using `> [!todo] Action Items` with checkboxes
- Each item: `- [ ] Detailed description of what to do`
- If no action items exist, output nothing
