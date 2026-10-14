[CmdletBinding()]
param(
    [string]$AwsExecutable = 'aws',
    [string]$Profile = 'resume-review-rds',
    [string]$Region = 'us-east-1'
)

# Read-only inventory. Does not start instances, change IAM, push images or migrate DBs.
$ErrorActionPreference = 'Stop'
$failed = $false
function Invoke-AwsCheck {
    param([string]$Label, [string[]]$Arguments)
    Write-Output "`n[$Label]"
    $result = & $AwsExecutable @Arguments --profile $Profile --region $Region --output json --no-cli-pager 2>&1
    if ($LASTEXITCODE -ne 0) {
        $script:failed = $true
        Write-Output "FAILED: $Label (check login, region and read permissions locally)"
        return
    }
    Write-Output $result
}

Get-Command $AwsExecutable -ErrorAction Stop | Out-Null
Invoke-AwsCheck 'Identity' @('sts', 'get-caller-identity')
if ($failed) { exit 1 }
Invoke-AwsCheck 'EC2' @('ec2', 'describe-instances', '--query', 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Type:InstanceType,PrivateIp:PrivateIpAddress,Name:Tags[?Key==`Name`].Value|[0],Role:IamInstanceProfile.Arn}')
Invoke-AwsCheck 'ECR' @('ecr', 'describe-repositories', '--query', 'repositories[].{Name:repositoryName,Uri:repositoryUri}')
Invoke-AwsCheck 'RDS' @('rds', 'describe-db-instances', '--query', 'DBInstances[].{Id:DBInstanceIdentifier,State:DBInstanceStatus,Engine:Engine,Public:PubliclyAccessible}')
Invoke-AwsCheck 'S3' @('s3api', 'list-buckets', '--query', 'Buckets[].Name')
Invoke-AwsCheck 'CloudFront' @('cloudfront', 'list-distributions', '--query', 'DistributionList.Items[].{Id:Id,Domain:DomainName,Status:Status}')
Invoke-AwsCheck 'SSM' @('ssm', 'describe-instance-information', '--query', 'InstanceInformationList[].{Id:InstanceId,Status:PingStatus}')
Invoke-AwsCheck 'OIDC' @('iam', 'list-open-id-connect-providers')
if ($failed) { exit 1 }
Write-Output "`nInventory complete. Resource presence does not establish deployment readiness."
