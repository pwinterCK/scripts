#!/usr/bin/env python
# ALGORITHM OF generate_report() COMING FROM https://gist.github.com/Eyjafjallajokull/4e917414cfb191391f9e51f6a8c3e46a
import re
import boto3
import csv
from botocore.exceptions import ClientError
import argparse
import time
from termcolor import colored
import os 
import sys
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
 
# ARGS 
parser = argparse.ArgumentParser(description="THIS SCRIPT WILL GENERATE A DETAILLED AUDIT OF SNAPSHOTS OVER ALL AWS REGIONS OR THE SPECIFIED REGIONS. A REPORT WILL BE GENERATED FOR EACH REGION AND REPORTS WILL BE ARCHIVED INSIDE A FOLDER") 
parser.add_argument("-r", "--region", type=str, help ="Will run this script only for the specified region")
parser.add_argument("-e", "--email",type=str, help="Will send the email to the given recipient")
args = parser.parse_args()

# GET REGIONS 
client = boto3.client('ec2')
if args.region: 
    regions = [args.region]
else:
    regions = [region['RegionName'] for region in client.describe_regions()['Regions']]
 
# GET ALL SNAPS 
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

# PARSE SNAP STANDARD DESCRIPTION 
def parse_description(description):
    regex = r"^Created by CreateImage\((.*?)\) for (.*?) "
    matches = re.finditer(regex, description, re.MULTILINE)
    for matchNum, match in enumerate(matches):
        return match.groups()
    return '', ''

# GENERATE REPORT 
def generate_report(region):
    with open('report_snaps_'+region+'.csv', 'w') as csvfile:
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


attachements = [] 

# ITERATE ON REGION TO GENERATE REPORT
for region in regions:
    if not get_snapshots(region):
        print("Skipping region no snapshots for " + region)
    else:
        try: 
            print ("Generating report for " + region)
            generate_report(region)
            attachements.append('report_snaps_'+region+'.csv')
        except Exception as e: 
                print(e)

if args.email:
    # DO NOT ITERATE ON REGION TO USE SES BECAUSE THE SERVICE MIGHT NOT BE AVAILABLE FOR ALL REGIONS 
    client = boto3.client('ses',region_name='us-east-1')
    MESSAGE = MIMEMultipart()
    MESSAGE['Subject'] = 'MONTHLY REPORT FOR FINDING USELESS SNAPSHOTS OVER AWS REGIONS'
    SENDER = MESSAGE['From'] = 'donotreply@crossknowledge.com'
    RECIPIENT = MESSAGE['To'] = args.email
    MESSAGE.preamble = 'Multipart message.\n'
    ATTACHMENT = MIMEText('Please find in attachement the report about useless snaps over AWS regions. The file must be analysed in order to find the useless snapshots and delete them')
    MESSAGE.attach(ATTACHMENT)
    for attachment in attachements:
        ATTACHMENT = MIMEApplication(open(attachment, 'rb').read())
        ATTACHMENT.add_header('Content-Disposition', 'attachment', filename=attachment) 
        MESSAGE.attach(ATTACHMENT)
        RAW_MESSAGE = {
                'Data': MESSAGE.as_string()
                }
        #SEND EMAIL WITH ALL ATTACHEMENTS USING SES
    try:
        response = client.send_raw_email(
                Destinations=[RECIPIENT,],
                RawMessage=RAW_MESSAGE,
                Source=SENDER
                )
    except Exception as e:
        print colored("REPORT HAS NOT BEEN SENT: "+ e,"red")

    if response:
        print colored("REPORT HAS BEEN SENT SUCCESSFULLY TO " + args.email ,"green")

# ARCHIVE REPORTS 
timestr = time.strftime("%Y%m%d-%H%M")
os.system('mkdir reports_snapshots_%s; mv report_snaps_*.csv reports_snapshots_%s'%(timestr,timestr)) 

