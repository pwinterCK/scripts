#!/usr/bin/env python
import re
import csv
import json
import boto3
import os
import sys
import argparse 
from botocore.exceptions import ClientError
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart

parser = argparse.ArgumentParser(description="THIS SCRIPT WILL GENERATE 3 REPORTS ABOUT UNUSED SGS,VOLUMES,SNAPSHOTS OVER AWS AZ(S)") 
parser.add_argument("-r", "--region", type=str, help="IF NOT SPECIFIED THE SCRIPT WILL RUN WITH THE CURRENT REGION OF BOTO3 USER. USE all FOR ALL REGIONS")
args = parser.parse_args()

#INIT
if not args.region:
    session = boto3.session.Session()
    region = session.region_name
    ec2_client = boto3.client('ec2', region_name=region)
    ec2_resource = boto3.resource('ec2', region_name=region)
else:
    if not args.region == "all": 
        region = args.region
    else:
        session = boto3.session.Session()
        region = session.region_name
        ec2_client = boto3.client('ec2', region_name=region)
        regions = [region['RegionName'] for region in ec2_client.describe_regions()['Regions']]

#GET SG NAME BY ID
def get_sg_name(sg_id,region):
    if not sg_id: return 'ID NOT SPECIFIED'
    try:
        ec2_client = boto3.client('ec2', region_name=region)
        requestObj = ec2_client.describe_security_groups(GroupIds=[sg_id,])
        sg_name_dict = requestObj['SecurityGroups']
        for name in sg_name_dict:
            return str(name['GroupName'])
    except ClientError as e :
        print(e)

#GET SNAPS 
def get_snapshots(region):
    ec2_region = boto3.client('ec2', region_name=region)
    return ec2_region.describe_snapshots(OwnerIds=['self'])['Snapshots']

# DOES THE VOLUME EXIST ?
def volume_exists(volume_id,region):
    if not volume_id: return ''
    try:
        ec2_region = boto3.client('ec2', region_name=region)
        ec2_region.describe_volumes(VolumeIds=[volume_id])
        return True
    except ClientError:
        return False

# DOES THE INSTANCE EXIST ?
def instance_exists(instance_id,region):
    if not instance_id: return ''
    try:
        ec2_region = boto3.client('ec2', region_name=region)
        ec2_region.describe_instances(InstanceIds=[instance_id])
        return True
    except ClientError:
        return False

    # DOES THE AMI EXIST ?
def image_exists(image_id,region):
    if not image_id: return ''
    try:
        ec2_region = boto3.client('ec2', region_name=region)
        requestObj = ec2_region.describe_images(ImageIds=[image_id,])
        if not requestObj["Images"]:
            return False
        return True
    except ClientError:
        return False

# PARSE SNAP STANDARD DESCRIPTION TO EXTRACT AMI IF POSSIBLE
def parse_description(description):
    regex = r"^Created by CreateImage\((.*?)\) for (.*?) "
    matches = re.finditer(regex, description, re.MULTILINE)
    for matchNum, match in enumerate(matches):
        return match.groups()
    return '', ''

def generate_report_unused_sgs(region):
    print('Generating Unused SGS report for '+region+' ...')
    # RAYRAYS				
    ec2_client = boto3.client('ec2', region_name=region)
    all_sgs = []
    sgs_in_use = []
    sgs_dict = ec2_client.describe_security_groups()
    sgs = sgs_dict['SecurityGroups']

    # ADD DEFAULT AND SGS STARTING WITH AWSEB TO SGS IN USE
    for obj in sgs:
        if obj['GroupName'] == 'default' or obj['GroupName'].startswith('awseb'):
            sgs_in_use.append(obj['GroupId'])
        all_sgs.append(obj['GroupId'])

    # FIND USED SGS BY EC2
    instances_dict = ec2_client.describe_instances()
    reservations = instances_dict['Reservations']
    for reservation in reservations:
        for j in reservation['Instances']:
            for k in j['SecurityGroups']:
                if k['GroupId'] not in sgs_in_use:
                    sgs_in_use.append(k['GroupId'])
                for m in j['NetworkInterfaces']:
                    for n in m['Groups']:
                        if n['GroupId'] not in sgs_in_use:
                            sgs_in_use.append(n['GroupId'])
    
    # FIND USED SGS BY ELB
    elb_client = boto3.client('elb', region_name=region)
    elb_dict = elb_client.describe_load_balancers()	
    for i in elb_dict['LoadBalancerDescriptions']:
        for j in i['SecurityGroups']:
            if j not in sgs_in_use:
                sgs_in_use.append(j)
    
    # FIND USED SGS BY ELB2
    elb2_client = boto3.client('elbv2', region_name=region)
    elb2_dict = elb2_client.describe_load_balancers()
    for i in elb2_dict['LoadBalancers']:
        for j in i['SecurityGroups']:
            if j not in sgs_in_use:
                sgs_in_use.append(j)
    
    # FIND USED SGS BY RDS	
    rds_client = boto3.client('rds', region_name=region)
    rds_dict = rds_client.describe_db_security_groups()
    for i in rds_dict['DBSecurityGroups']:
        for j in i['EC2SecurityGroups']:
            if j not in sgs_in_use:
                sgs_in_use.append(j)
    
    # BUILD CANDIDATES LIST FOR DELETION (all_sgs - sgs_in_use = candidates)
    candidates = []
    for sg in all_sgs:
        if sg not in sgs_in_use:
            candidates.append(sg)
    
    # GENERATE REPORT : UNUSED SECURITY GROUPS + WRITE FILE IN /tmp/sgs_to_delete_region.txt
    list_ids = str(candidates).strip('[]').replace("'", "")
    url = "https://" + region +".console.aws.amazon.com/ec2/v2/home?region="+region+"#SecurityGroups:search=" + list_ids + ";sort=groupId"
    if list_ids:
        with open("/tmp/sgs_to_delete_" + region +".txt","w+") as f2:
            print >> f2, "==== CONSOLE URL " + url + "===="
            for sg_id in candidates:
                print >> f2, sg_id + " / " + get_sg_name(sg_id,region)
    else:
        with open("/tmp/sgs_to_delete_" + region +".txt","w+") as f2:
            print >> f2, "No unused security groups for this region " + region

def generate_report_unused_volumes(region):
    print('Generating Unused VOLUMES report for '+ str(region)+' ...')
    # GENERATE REPORT : UNUSED VOLUMES + WRITE FILE IN /tmp/unused_volumes_region.txt
    ec2 = boto3.resource('ec2',region_name=region)
    string_ids = "false"
    candidates = []
    for vol in ec2.volumes.all():
        if vol.state=='available':
            candidates.append(vol.id)
            string_ids = str(candidates).strip('[]').replace("'", "")
            if not string_ids =="false":
                url = "https://" + region +".console.aws.amazon.com/ec2/v2/home?region="+region+"#Volumes:search=" + string_ids + ";sort=groupId"
                with open("/tmp/unused_volumes_"+region+".txt","w+") as f:
                    print >> f, "==== CONSOLE URL :" + url +"===="
                    for candidate in candidates:
                        print >> f, candidate
            else:
                print ('IN else')
                with open("/tmp/unused_volumes_"+region+".txt","w+") as f:
                    print >> f, "No unused volumes for this region " +region
# WRITE FILE ANYWAY
    if string_ids == "false":
        with open("/tmp/unused_volumes_" + region + ".txt", "w+") as f:
            print >> f, "No unused volumes for this region " + region

# GENERATE REPORT : UNUSED SNAPSHOTS + WRITE FILE IN /tmp/report_snaps_region.csv 
def generate_report_unused_snaps(region):
    if get_snapshots(region):
        print('Generating Unused SNAPSHOTS report for '+ region + ' ...')
        with open('/tmp/report_snaps_'+region+'.csv','w') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'Snapshot ID',
                'Description',
                'Started on',
                'Size (GB)',
                'Volume ID',
                'Volume exists?',
                'Instance ID',
                'Instance exists?',
                'AMI ID',
                'AMI exists?'])
            for snap in get_snapshots(region):
                instance_id, image_id = parse_description(snap['Description'])
                writer.writerow([
                    snap['SnapshotId'],
                    snap['Description'],
                    snap['StartTime'],
                    str(snap['VolumeSize']),
                    snap['VolumeId'],
                    str(volume_exists(snap['VolumeId'],region)),
                    instance_id,
                    str(instance_exists(instance_id,region)),
                    image_id,
                    str(image_exists(image_id,region)),
                    ])
    else:
        print('No snaps found for this region ' + str(region))
        with open('/tmp/report_snaps_'+str(region)+'.csv','w') as csvfile:
            print >> csvfile, "No snaps found for this region " +str(region)
    
 
def generate_and_send_email(region,attachments):

    # CONSTRUCT AND SEND EMAIL ALWAYS SEND FROM EU SINCE SES IS NOT DEPLOYED EVERYWHERE
    MESSAGE = MIMEMultipart()
    MESSAGE['Subject'] = 'MONTHLY REPORT FOR AWS AZ ' +region+' ABOUT UNUSED SGS/VOLUMES/SNAPSHOTS'
    SENDER = MESSAGE['From'] = 'donotreply@crossknowledge.com'
    RECIPIENT = MESSAGE['To'] = 'pascal.winter@crossknowledge.com' 
    MESSAGE.preamble = 'Multipart message.\n'
    ATTACHMENT = MIMEText('Please find in attachment three reports; each file must be analysed separately in order to find and delete unecessary snapshots,volumes and security groups for the following AWS AZ: '+region)
    MESSAGE.attach(ATTACHMENT)
    
    # ADD EMAILS ATTACHMENTS 
    for attachment in attachments:
        if os.path.exists(attachment):
            ATTACHMENT = MIMEApplication(open(attachment, 'rb').read())
            ATTACHMENT.add_header('Content-Disposition', 'attachment', filename=attachment) 
            MESSAGE.attach(ATTACHMENT)
            RAW_MESSAGE = {
                    'Data': MESSAGE.as_string()
                }
        else:
            ATTACHMENT = MIMEText('SOMETHING WENT WRONG WHEN ATTACHING THE FOLLOWING REPORT: '+ attachment)
            MESSAGE.attach(ATTACHMENT)
            RAW_MESSAGE = {
                    'Data': MESSAGE.as_string()
                    }

    # SEND EMAIL USING SES
    try:
        client = boto3.client('ses',region_name='eu-west-1')
        response = client.send_raw_email(
            Destinations=[RECIPIENT,],
            RawMessage=RAW_MESSAGE,
            Source=SENDER
        )
    except Exception as e:
        return False
    if response: 
        print ('Report for' + region +' has been sent successfully by email')
    else:
        return False 

# SHOOT
if args.region =="all":
    session = boto3.session.Session()
    region = session.region_name
    ec2_client = boto3.client('ec2', region_name=region)
    regions = [region['RegionName'] for region in ec2_client.describe_regions()['Regions']]
    for az in regions:
        try:
            attachments = []
            # BUILD ATTACHMENT HERE BECAUSE NOT WORKING
            generate_report_unused_sgs(az)
            generate_report_unused_volumes(az)
            generate_report_unused_snaps(az)
            if os.path.exists('/tmp/sgs_to_delete_'+str(az)+'.txt'):
                attachments.append('/tmp/sgs_to_delete_'+str(az)+'.txt')
            if os.path.exists('/tmp/unused_volumes_'+str(az)+'.txt'):
                attachments.append('/tmp/unused_volumes_'+str(az)+'.txt')
            if os.path.exists('/tmp/report_snaps_'+str(az)+'.csv'):
                attachments.append('/tmp/report_snaps_'+str(az)+'.csv')
        except Exception as e:
            print(e) 
        try:
            generate_and_send_email(az,attachments)
        except Exception as e:
            print(e)
    
else:
    try:
        generate_report_unused_sgs(region)
        generate_report_unused_volumes(region)
        generate_report_unused_snaps(region)
        attachments = []
        if os.path.exists('/tmp/sgs_to_delete_'+str(region)+'.txt'):
            attachments.append('/tmp/sgs_to_delete_'+str(region)+'.txt')
        if os.path.exists('/tmp/unused_volumes_'+str(region)+'.txt'):
            attachments.append('/tmp/unused_volumes_'+str(region)+'.txt')
        if os.path.exists('/tmp/report_snaps_'+str(region)+'.csv'):
            attachments.append('/tmp/report_snaps_'+str(region)+'.csv')
        generate_and_send_email(region,attachments)
    except Exception as e: 
        print(e)
