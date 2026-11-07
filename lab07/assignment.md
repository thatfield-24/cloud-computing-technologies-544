Output of terraform version and aws sts get-caller-identity (hide the account number).
![Terraform version](images/terraform_version.png)
Part A: the plan before the first apply, the second apply showing No changes , the in-place update plan ( ~ ) and the replacement plan ( -/+ ), with a sentence on why -/+ is the one to be careful about.
![Terraform Plan](images/terraform_plan.png)
First Apply
![Terraform First Apply](images/terraform_apply.png)
Second Apply
![Terraform Second Apply](images/terraform_second.png)

Output of terraform fmt , terraform validate and the last lines of terraform plan showing the number of resources to add.

Output of app_smoke_test.py with all nine checks passing, and a screenshot of the advisor page.

Steps 1 to 3: your effort table with line counts, the terraform graph output with your sentence, and the No changes plan with your sentence comparing it to running the bash script twice.

Steps 4 and 5: the plan for cache_seconds = 60 , the instance refresh status and new CACHE_SECONDS=60 line, and the drift plans with your sentence about ensure_target_group.

Steps 6 and 7: the IAM simulator results with your sentence about the advisor tier, and the No changes plan, the grep -c count of 0 and your sentences about ignore_changes.

Steps 8 and 9: the fallback answers with the gemini_error journal line and your sentence about silent fallback, and the completed Lambda table with your answer to question 4.


Step 10: the terraform destroy plan and total time, your cost estimate (hours multiplied by the hourly cost), and the verification commands showing nothing remains.

## Short answers: 
How Terraform is like AWS Lambda and where the comparison stops, what Terraform did not make easier

## Review Questions:
[Section 13.1 review questions](review_questions.md)
