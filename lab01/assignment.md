Lab01_AWS_Account_Setup_MFA
MFA helps to verify that who is logging in is who the intended user actually is. This can help prevent unwanted access which is especially important to have enabled for the root account because a threat actor could gain access to the entire system. The concept of least-privlege is extremely important as it gives poeple only the permissions they need for the immediate work being done. If the user needs more permissions they can switch to a higher privileged account to complete the larger scale changes. 

![Root MFA](root_mfa.png)
![IAM User](iam_user.png)
![IAM User MFA](iam_user_mfa.png)
![IAM User AccessKey](iam_user_accesskey.png)


Lab02_Docker_Linux_Container_Setup
A docker image is like a cookie cutter where you can use it to easily recreate the shape or in this case recreate a specific macine type. Similarily, a docker container is like the actual cookie that is made, in this case it is the specific instance of the machine. 

![Docker version](docker_version.png)
![Docker Hello World](docker_hello_world.png)
![Docker OS Release](docker_os_release.png)
![Docker ps -a before](docker_ps-a_before.png)
![Docker ps -a after](docker_ps-a_after.png)