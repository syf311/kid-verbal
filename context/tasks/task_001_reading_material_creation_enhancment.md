
## Status: DONE

## Objective

1. Have function to have AI build questions and answers customized for kid grade level 

## Requirements

1. For imported reading material, after clicking batch import, add a Generate by AI button. This can have AI scan the source of the reading material, and run the prompt of such: "Please build 10 multi choice questions and answers for the article in the link for grade level {xyz}. And send back a separated question list and answer list. Question list should be numbered and put in the question box. And Answer list should NOT be numbered and be put in the answer box. Answers NEED TO BE evenly distributed across A, B, C, D".  
2. Then it should work seamlessly with existing import all button
3. We will have OpenAI API as our AI integration point. And api key should be stored in database and configuration page so we can later dynamically  change and save it and no worry to checkin the code and leak. openai api key would work later on across the site for all AI featuers.
4. we should have a way to update kid  grade level which will be later used across the site for AI to understand corresponding complexity
5. Fix previous bugs: 
	1. after import, look at current kid, and make sure the imported material assigned to the kid




## Acceptance Criteria

1. all existing functions should still work
2. clicking batch import->generate by ai->import all should work
3. configuration page can save openai api key and it should work for all ai features across the site later on.
4. openai apikey not visible in any places in the code for safety purpose
