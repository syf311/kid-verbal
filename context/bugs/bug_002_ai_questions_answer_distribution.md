## Status: Fixed

## Objective

Fix the AI question generation prompt so correct answers are randomly distributed across A, B, C, D instead of clustering on B and C.

## Description

When using "Generate by AI" for reading material questions, the correct answers are heavily biased toward B and C (sometimes all B). This makes the quiz predictable and reduces learning value.

## Root Cause

The prompt in `/api/materials/<id>/questions/generate-ai` (app.py ~line 4925) has two issues:

1. **Example answers only show B and A** — The few-shot example at the end of the prompt only demonstrates `B` and `A` as answers. LLMs anchor heavily on example patterns, so the model mimics this narrow distribution.
2. **Instruction is weak** — Line 4932 says "roughly 2-3 of each letter" but the example contradicts this, and the model treats examples as more authoritative than instructions.

## Fix

1. Expand the example answers section to show all four letters with a realistic distribution (e.g., `B\nD\nA\nC\nA\nB\nD\nC\nA\nC`)
2. Strengthen the randomness instruction — e.g., "The correct answer position MUST be randomized across A, B, C, D. Do NOT put the correct answer in the same position repeatedly."
3. Optionally add a system message to reinforce answer randomization

## Acceptance Criteria

1. AI-generated answers are distributed across A, B, C, D (no more than 4 of any single letter in 10 questions)
2. No single letter dominates the answer set
3. Questions and parsing still work correctly after prompt changes
