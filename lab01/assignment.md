Lab01_AWS_Account_Setup_MFA
One paragraph reflecting on why root user MFA and least-privilege IAM users matter for cloud security.
MFA helps to verify that who is logging in is who the intended user actually is. This can help prevent unwanted access which is especially important to have enabled for the root account because a threat actor could gain access to the entire system. The concept of least-privlege is extremely important as it gives poeple only the permissions they need for the immediate work being done. If the user needs more permissions they can switch to a higher privileged account to complete the larger scale changes. 

![Root MFA](root_mfa.png)
![IAM User](iam_user.png)
![IAM User MFA](iam_user_mfa.png)
![IAM User AccessKey](iam_user_accesskey.png)

