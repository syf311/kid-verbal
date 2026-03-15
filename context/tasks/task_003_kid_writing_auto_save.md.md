
## Status: Done

## Objective

1. for kid writing, need to have a way to auto save so they do not 

## Requirements

1. when kid is doing writing, need to periodically save. we can do local checkpoint every 5mins second if possible. ok to do server approach if client approach not working
2. need to have a nice way to revert to previous save point to avoid kid accidentally delete written content. (e.g., snapshot by checkpoint time, like last 5th min 10th min, etc)
3. can clear local checkpoint once submitted to server


## Acceptance Criteria

1. all existing functions should still work
2. need to see 5th min, 10th min... checkpoints and can revert to any of it
3. every change is auto saved leave page or app and come back can still see all the auto saved content and checkpoints

