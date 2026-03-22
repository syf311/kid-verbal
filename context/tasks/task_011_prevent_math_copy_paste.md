## Status: Done

## Objective

Prevent kids from selecting, copying, and pasting math question text during tests and practice to discourage sending questions to ChatGPT for answers.

## Scope

Apply to the math bank test taking page (`math_bank_test.html`):
- Disable text selection on question text and choices via CSS (`user-select: none`)
- Disable right-click context menu on the test area
- Disable Ctrl+C / Cmd+C keyboard shortcut during the test

Note: This is a deterrent, not a bulletproof solution. Determined users can still screenshot or use browser dev tools. The goal is to remove the easy path.

## Acceptance Criteria

1. Question text and choices cannot be selected or highlighted during a math bank test
2. Right-click context menu is disabled on the test page
3. Ctrl+C / Cmd+C does not copy text from the test
4. Radio buttons and other interactive elements still work normally
