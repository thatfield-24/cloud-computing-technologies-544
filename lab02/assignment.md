# AWS_CLI_EC2_EnvVariables
You should never commit enviornment variables to a repository, even if it is private, as if the repository is ever made public people can use the environment variables to mimic your business. In the case that there were any Github or AWS credentials on there it could be lead to the same issues as committing those alone would do. AWS credentials can lead to account takeover or overall data destruction. Github tokens could also allow an insider threat to steal the data and pretty much one-to-one recreate a proprietary software.  

## Decomposed AWS Command
aws ec2 run-instances --image-id ami-001cbfee94278a792 --instance-type t3.micro
All aws commands start with the keyword aws
The next part of the command "ec2" is the specific aws service we want to interact with
"run-instances" is the operation type which tells the service what action to take
Finally the next parts of the command are all parameters. This allows us to pass specific values to make the action more specific. In this case "--image-id" and "instance-type" are both parameters while "ami-001cbfee94278a792" and "t3.micro" are the values given to these parameters
![Decomposed AWS Command](images/decomposed_aws_command.png)
Red Arrow is the AWS Service Type
Blue Arrow is the Operation Type
Pink Arrows are Parameters that can be added

## Supporting Images
![Hello From IP](images/hello_from_ip.png)
![Git Status](images/gitstatus.png)
![Git Ignore](images/git_ignore.png)
![Create Instances](images/create_instances.png)
![Delete Instances](images/delete_instance.png)



