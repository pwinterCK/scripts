#!/usr/bin/env python
#PWIPWI 16/11/2018
import boto3
import argparse
from termcolor import colored
import time 
import sys
import os
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart

## TO DO : CREATE REPORT + EMAIL
parser = argparse.ArgumentParser(description="PLEASE READ CAREFULLY ; THIS SCRIPT WILL AUDIT UNUSED VOLUMES (BASED ON THEIR STATE) OVER ALL AWS REGIONS OR WILL DELETE THEM IF -d OPTION IS SPECIFIED. A REPORT WILL BE SENT BY EMAIL IF -e OPTION IS SPECIFIED") 
parser.add_argument("-r", "--region", type=str, help="Will run the script only for the specified region")
parser.add_argument("-d", "--delete",help="Will delete unused SG for all infras", action="store_true")
parser.add_argument("-e", "--email",type=str, help="Will send the report by email to the given recipient")
args = parser.parse_args()

client = boto3.client('ec2')

if not args.delete:
    print colored("######################################################################","cyan")
    print colored("########################## DRYRUN=TRUE ###############################","cyan")
    print colored("######################################################################","cyan")
else:
    print colored("######################################################################","red")
    print colored("######################### DELETETION MODE ############################","red")
    print colored("######################################################################","red")

if args.email:
    print colored("######################################################################","green")
    print colored("############## REPORT OUTPUT FILE WILL BE SEND BY EMAIL ##############","green")
    print colored("######################################################################","green")
    
if args.region:
    print colored("######################################################################","magenta")
    print colored("############## SCRIPT WILL ONLY EXECUTED ON " +args.region+ " ################","magenta")
    print colored("######################################################################","magenta")

# RETRIEVE ALL REGIONS DYNAMICALLY 
if not args.region: 
    regions = [region['RegionName'] for region in client.describe_regions()['Regions']]

# CHECK THAT THE REGION EXISTS
else: 
    regions = [args.region]
    if args.region not in regions: 
        print("Weird region specified")
        exit()

# ITERATE ON REGIONS
for region in regions: 
        list_ids = []
        candidates = []
        print colored("========== LOOKING FOR UNUSED VOLUMES IN " + region + " =============", "yellow")
        ec2=boto3.resource('ec2', region_name = region) 
        
        # GET ALL VOLUMES AND CHECK THEIR STATE 
        for vol in ec2.volumes.all(): 
            if vol.state=='available':
                candidates.append(vol.id)
                list_ids =  str(candidates).strip('[]').replace("'", "")
                print (vol.id + " SIZE " + str(vol.size) + "GB :" + "CREATED ON " + str(vol.create_time) + " NOT USED IN " + region)
                # IF DELETE
                if not args.delete:
                    try:
                        # GET BACK THE CLIENT FOR THE RIGHT REGION NOT THE DEFAULT ONE OF BOTO
                        client = boto3.client('ec2', region_name=region) 
                        client.delete_volume(VolumeId=vol.id,DryRun=True)
                    except Exception as e: 
                        print colored (e, "red")
                else: 
                    try:# GET BACK THE CLIENT FOR THE RIGHT REGION NOT THE DEFAULT ONE OF BOT
                        client = boto3.client('ec2', region_name=region)
                        client.delete_volume(VolumeId=vol.id,DryRun=True)
                    except Exception as e:
                        print colored (e, "red")


        if list_ids: 
            # AMAZON CONSOLE URL OF VOLUMES TO BE DELETED FOR THE GIVEN REGION 
            url = "https://" + region +".console.aws.amazon.com/ec2/v2/home?region="+region+"#Volumes:search=" + list_ids + ";sort=groupId"
            with open("unused_volumes_"+region+".txt","w+") as f:
                print >> f, url
                for candidate in candidates:
                    print >> f, candidate
        else:
            print colored("=========== " + region + " DOES NOT HAVE ANY UNUSED VOLUMES =======", "green")

# ONE FILE BUT REGION COULD HAVE NO VOLUMES UNUSED
if not args.region:
    try: 
        os.system('cat unused_volumes_*.txt >> unused_Volumes_all_regions.txt;')
    except Exception as e: 
        print colored(e, "red")
else: 
    if os.path.exists("unused_volumes_"+args.region+".txt"):
        os.system('mv unused_volumes_*.txt unused_Volumes_all_regions.txt;')
    else:
        print colored("No report to generated for "+args.region,"red")
        exit() 

# SEND EMAIL
if (args.email and os.path.exists('unused_Volumes_all_regions.txt') == True):
    # DO NOT ITERATE ON REGION TO SEND EMAIL BECAUSE SES MIGHT NOT BE WORKING
    client = boto3.client('ses',region_name='us-east-1')
    MESSAGE = MIMEMultipart()
    MESSAGE['Subject'] = 'MONTHLY REPORT FOR UNUSED VOLUMES OVER AWS REGIONS'
    SENDER = MESSAGE['From'] = 'donotreply@crossknowledge.com'
    RECIPIENT = MESSAGE['To'] = args.email
    MESSAGE.preamble = 'Multipart message.\n'
    ATTACHMENT = MIMEText('Please find in attachement the report about unused volumes over AWS regions. All the SG ids in the file are candidates for deletion')
    MESSAGE.attach(ATTACHMENT)
    ATTACHMENT = MIMEApplication(open('unused_Volumes_all_regions.txt', 'rb').read())
    ATTACHMENT.add_header('Content-Disposition', 'attachment', filename='unused_Volumes_all_regions.txt')
    MESSAGE.attach(ATTACHMENT)
    RAW_MESSAGE = {
            'Data': MESSAGE.as_string()
            }
    # SEND THE EMAIL USING SES
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

# ARCHIVE REPORT 
try:
    timestr = time.strftime("%Y%m%d-%H%M")
    os.system('mkdir unused_volumes_all_regions_%s; mv unused_Volumes_all_regions.txt unused_volumes_all_regions_%s; rm unused_volumes*.txt'%(timestr,timestr))
except Exception as e: 
    print colored(e, "red")
