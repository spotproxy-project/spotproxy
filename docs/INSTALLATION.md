This will guide you through the AWS VM setup process of the instance manager component of SpotProxy. The purpose of this document is to familiarize you with the process, since for the purposes of artifact evaluation, most of these steps will be repeated for the other components. 

Note: this evaluation can be done mostly on free AWS resources (except for the use of Elastic IPs which are charged less than a dollar).

## Setup instructions:
1. Setup an AWS account, create an IAM user (give it Full EC2 access permissions), and obtain its AWS access key and AWS secret access key. 
2. Create a AWS VM running Ubuntu 22.04, with a security group allowing all TCP traffic (for the convenience of artifact evaluation). This will be used for the instance manager component of SpotProxy. 
3. SSH into the VM. 
4. Install [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
5. To use your IAM credentials to authenticate the Terraform AWS provider, set the `AWS_ACCESS_KEY_ID` environment variable.
```bash
export AWS_ACCESS_KEY_ID=
```
6. Now, set your secret key. 
```bash
export AWS_SECRET_ACCESS_KEY=
```

## Basic test:
1. On a separate machine (e.g., your host machine), ensure the AWS VM's public IP (this can be obtained for example from the AWS console) can be pinged.
```bash
ping <AWS-VM-PUBLIC-IP>
```

2. Check if the AWS CLI is configured correctly. 
The following command will give you the instances that are currently within the us-east-1 region, in the form of the table. 
```bash
aws ec2 describe-instances --region us-east-1 --query "Reservations[*].Instances[*].[InstanceId,State.Name]" --output table
```