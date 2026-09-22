---
name: review
description: Review an implemented change for correctness, regressions, and task fit.
---

# Review

Review the implementation against the original task, plan, workspace diff, and
verification evidence. Focus on concrete correctness or regression risks; do
not expand the requested scope.

Write `review.md` in the run's artifact directory with findings ordered by
severity and a short verdict.

Choose `approved` when there are no material findings. Choose
`changes_requested` when implementation work can address the findings. Choose
`blocked` when the review cannot be completed with the available evidence or
access.
