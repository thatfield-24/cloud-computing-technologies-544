# Why should you use separate IAM roles instead of one shared role?
Using separate IAM roles enforces the principle of least privilege by ensuring that each EC2 instance receives only the exact permissions needed to perform its specific function. In this the uploader instance requires write access (s3:PutObject) while the viewwer instance only requires read access (s3:GetObject and s3:ListBucket). If a single shared role were used, an attacker could overwrite or corrupt stored data or even replace it with a malicious file. Separating these permissions into distinct roles minimizes the blast radius of a potential security compromise and ensures complete isolation between write and read operations

# Why embed code directly into user-data instead of using Git?
By encoding the source code directly into the launch template's script the EC2 instance receives all neessary files during its initial boot sequence. This allows the deployment to initiaize without needing Git SSH keys, personal access tokens, or S3 read permissions.

Screenshot of Apps Folder
![Screenshot of apps folders](images/apps.png)

Successful Upload
![Successful Upload](images/successful.png)

PNG Upload
![PNG Upload](images/pngUpload.png)

Text File Too Large
![Text File Too large](images/tooLarge.png)

Successful View
![Successful View](images/successfulView.png)

Second File Uploaded
![Second File Uploaded](images/secondFile.png.png)

Showing Both Templates
![Showing Both Templates](images/Templates.png)

Second Launch Template Version
![Second Launch Template Version](images/secondLaunchTemplate.png)

IAM Role Uploader
![IAM Role Uploader](images/IAMUploader.png)

IAM Role Viewer
![IAM Role Viewer](images/IAMViewer.png)

IP Addresses of the Apps
![IP Addresses of the Apps](images/appIPAddresses.png)

Successful Deletion
![Successful Deletion](images/deleteSuccessful.png)

