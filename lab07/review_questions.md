# Lab 07: Review Questions

| Topic | What this lab did | The question to answer | Answer |
| :--- | :--- | :--- | :--- |
| **Declarative and imperative** | Terraform compares files, state and AWS, then decides the steps | Give one thing the imperative bash version could do that is hard in Terraform, and one thing Terraform did that the bash version never did | |
| **State file** | `terraform.tfstate` records every resource and ID | What would happen if you lost it? What would happen if two people applied from different copies? How do teams solve this? | |
| **Secrets in state** | The Gemini parameter uses `ignore_changes` and the key is stored with the CLI | Where else could a secret reach the state or plan file? Why is a plan file also sensitive? | |
| **Plan before apply** | `plan -out` then `apply tfplan` | What does reading a plan protect you from? Which plan symbol worries you most, and why? | |
| **Version pinning** | `~> 5.0` and the lock file | What could go wrong with no version pin, and why do we commit `.terraform.lock.hcl`? | |
| **`for_each` or `count`** | Both tiers come from one map, and SSH uses `count` | Why does `for_each` handle removing one tier better than `count` would? | |
| **Ownership** | Terraform owns a new security group instead of editing lab02's | What goes wrong when a tool and a person both edit the same resource? | |
| **Drift** | You changed a health check by hand | How could a team find drift automatically and regularly? Who should be allowed to change things by hand? | |
| **Blast radius** | Changing `cache_seconds` touched only the weather tier | What decides how much one change touches, and how could you shrink it further? | |
| **Least privilege** | Each role names one resource, and the policy refers to the resource's own ARN | Why is a reference safer than a typed-in ARN? | |
| **Terraform and Lambda** | Section 3 and Step 9 | In your own words: what does Terraform have in common with Lambda, and what is the one difference that matters most for how you would use each? | |
| **Destroy** | One command removes everything | Which resources would you protect from a careless `destroy` in a real environment, and how (look up `prevent_destroy`)? | |