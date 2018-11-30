#!/usr/bin/env python
#PWIPWI 15/11/2018
import boto3
from termcolor import colored
import time
import argparse
import sys
import os
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart

# ARGS 
parser = argparse.ArgumentParser(description="PLEASE READ CAREFULLY ; THIS SCRIPT WILL AUDIT (IF -l OPTION IS SPECIFIED OR NO OPTIONS) OR DELETE (IF -d OPTION IS SPECIFIED)ALL SECURITY GROUPS WHICH ARE NOT BEING USED EITHER BY EC2, RDS, ELB OR ALB && ARE NOT THE DEFAULT ONES && NOT STARTING WITH THE NAME awseb* FOR ALL REGIONS OVER AWS. IF YOU HAVE SGS UNDER WORK, AND YOU WOULD LIKE THIS SCRIPT TO NOT DELETE THEM, PLEASE FILL THE ARRAY DIRECTLY INSIDE THE SOURCE CODE OF THE SCRIPT LIKE THE FOLLOWING sg_manually_added=[\"sg-groupdID1\",\"sg-groupdID2\"]\n. EX usage: ./AWS_cleanup_unused_SGS_EC2.py -l -d -e pascal.winter@crossknowledge.com")

parser.add_argument("-d", "--delete",help="Will delete unused SG for all infras", action="store_true")
parser.add_argument("-r", "--region",type=str,help="The script will be run on this specific region only")
parser.add_argument("-e", "--email",type=str, help="Will send the email to the given recipient")
args = parser.parse_args()

# USELESS STUFF
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


# GET REGION LIST DYNAMICALLY // USING DEFAULT REGION TO CALL
client = boto3.client('ec2')
regions = [region['RegionName'] for region in client.describe_regions()['Regions']]

if args.region:
    regions_manually = [args.region]
    # IF ARG OF -r OPTION IS NOT IN THE DEFAULT LIST; BYE
    if args.region not in str(regions):
        print colored("THE REGION YOU SPECIFIED IN ARGUMENT DOES NOT MATCH THE DEFAULT LIST, DOUBLE CHECK YOUR REGION", "red")
        sys.exit() 
    else: 
        regions = regions_manually

# LIST OF SG MANUALLY ADDED THAT YOU SOMEHOW DONT WANT TO DELETE 
sg_manually_added = []

# ITERATE ON REGIONS
for region in regions:
    
        # INIT
        ec2_client = boto3.client('ec2', region_name=region)
	ec2_resource = boto3.resource('ec2', region_name=region)

        # WE WILL NEED IT 
        def get_sg_name(sg_id):
            if not sg_id: return 'ID NOT SPECIFIED'
            try:
                requestObj = ec2_client.describe_security_groups(GroupIds=[sg_id,])
                sg_name_dict = requestObj['SecurityGroups']
                for name in sg_name_dict:
                    return str(name['GroupName'])
            except ClientError:
                return False

        # DECLARE LISTS 
        all_sgs = []
	sgs_in_use = []
        
        # ADD sg_manually_added[] TO sgs_in_use[] 
        for sg_m in sg_manually_added:
            sgs_in_use.append(sg_m)
	    print colored(sg_m + " WILL NOT BE ADDED TO CANDIDATES FOR DELETION (MANUALLY ADDED)","green")
        
        print colored("=========== LOOKING FOR CANDIDATES TO DELETE IN " + region + " ============","yellow")
       
        # GET ALL SGS
	sgs_dict = ec2_client.describe_security_groups()
	sgs = sgs_dict['SecurityGroups']
	
        for obj in sgs:
                # CANNOT DELETE DEFAULT OR AWSEB ONE
                if obj['GroupName'] == 'default' or obj['GroupName'].startswith('awseb'):
                    sgs_in_use.append(obj['GroupId'])
                    print colored(obj['GroupName'] + " SG FOUND OR STARTING WITH AWSEB* ","red")
		all_sgs.append(obj['GroupId'])

        # GET INSTANCES DESCRIBE
	instances_dict = ec2_client.describe_instances()
	reservations = instances_dict['Reservations']
	
        # ADD SGS USED BY EC2 IN sgs_in_use[]
        for reservation in reservations:
            for j in reservation['Instances']:
                for k in j['SecurityGroups']:
                    if k['GroupId'] not in sgs_in_use:
                        sgs_in_use.append(k['GroupId'])
			# ADD SGS USED BY NETWORK INTERFACES IN sgs_in_use[] AND NOT ALREADY IN THE LIST
                        for m in j['NetworkInterfaces']:
                            for n in m['Groups']:
                                if n['GroupId'] not in sgs_in_use:
                                    sgs_in_use.append(n['GroupId'])

	# ADD SGS USED BY ELB IN sgs_in_use[]
	elb_client = boto3.client('elb', region_name=region)
	elb_dict = elb_client.describe_load_balancers()
	
        for i in elb_dict['LoadBalancerDescriptions']:
		for j in i['SecurityGroups']:
			if j not in sgs_in_use:
				sgs_in_use.append(j)

	# ADD SGS USED by ALB IN sgs_in_use[]
	elb2_client = boto3.client('elbv2', region_name=region)
	elb2_dict = elb2_client.describe_load_balancers()

	for i in elb2_dict['LoadBalancers']:
		for j in i['SecurityGroups']:
			if j not in sgs_in_use:
				sgs_in_use.append(j)
	
        # ADD SGS USED BY RDS IN sgs_in_use[]
	rds_client = boto3.client('rds', region_name=region)
	rds_dict = rds_client.describe_db_security_groups()

	for i in rds_dict['DBSecurityGroups']:
		for j in i['EC2SecurityGroups']:
			if j not in sgs_in_use:
				sgs_in_use.append(j)

    # CREATE CANDIDATES LIST OF CANDIDATES FOR DELETION
	candidates = []
	
        for sg in all_sgs:
		if sg not in sgs_in_use:
                    candidates.append(sg)
        
        # COUNT CANDIDATES FOR DELETION FINAL LIST 
        count = len(candidates)
       
        # CREATE URL TO SEE WHAT YOU WILL DELETE INSIDE AWS CONSOLE
        list_ids = str(candidates).strip('[]').replace("'", "")
        url = "https://" + region +".console.aws.amazon.com/ec2/v2/home?region="+region+"#SecurityGroups:search=" + list_ids + ";sort=groupId"

        # WRITE CANDIDATES FOR DELETION IN TXT FILES 
        timestr = time.strftime("%Y%m%d-%H%M%S")
        # SEND URL OF AWS CONSOLE WITH SG LIST IDS PER REGION IN LOG FILE
        with open("sgs_to_delete_" + region +"_"+ timestr + ".txt","w+") as f:
            if list_ids: 
                print >> f, "==== CONSOLE URL " + url
                for sg_id in candidates:
                    print >> f, sg_id

        # FOR EACH SGID TRY TO DELETE CANDIDATE ACCORDING TO ARGS 
        for candidate in candidates:
            sg_detail=ec2_client.describe_security_groups(GroupIds=[candidate])
           
            # SAVE DETAILS OF CANDIDATES FOR DELETIONS IF LOG IS ON 
            with open("sg_detail_deleted_" + candidate +"_"+ timestr + ".txt","w+") as f2:
                print >> f2, sg_detail 
           
            # DRY RUN
            if not args.delete:
                print colored(candidate + " / " + get_sg_name(candidate) + " IS NOT USED AND WILL BE DELETED","yellow")
                try:
                    ec2_client.delete_security_group(GroupId=candidate,DryRun=True)
                except Exception as e:
                    print colored(e, "red")
            
            # DELETE IS COMING                 
            else:
                try:
                    print colored(candidate + " / " + get_sg_name(candidate) + " IS NOT USED AND HAS BEEN DELETED","yellow")
                    # AT SOME POINT SOMEBODY WILL HAVE TO MODIFY THIS HARDCODED VALUE TO FALSE. SINCE WE ARE IN THE DELETE ARG SPECIFIED
                    ec2_client.delete_security_group(GroupId=candidate,DryRun=True)
                except Exception as e:
                    print colored(e,"red")
      
        # PRINT NUMBER OF CANDIDATES DELETED  
        if count == 0:
            print colored("======= " + region + " REGION IS ALREADY QUITE CLEAN WITHOUT UNUSED SG =======","green") 
        else:
            print colored("================= " + str(count) +  " CANDIDATES DELETED " + region + " ====================","cyan")
            print colored("================= " + url + " ====================", "green")
 
#ONE FILE FOR ALL REGIONS  
try: 
    os.system('cat sgs_to_delete_*.txt >> all_sgs_deleted_all_regions.txt')
except Exception as e:
    print colored(e,"red") 
#SENDING REPORT BY EMAIL IF SPECIFIED (COULD BE USED BY CRON OR LAMBDA)
if args.email:
    # DO NOT ITERATE ON REGION TO SEND EMAIL BECAUSE SES MIGHT NOT BE WORKING
    client = boto3.client('ses',region_name='us-east-1')
    MESSAGE = MIMEMultipart() 
    MESSAGE['Subject'] = 'MONTHLY REPORT FOR UNUSED SECURITY GROUPS OVER AWS REGIONS'
    SENDER = MESSAGE['From'] = 'donotreply@crossknowledge.com'
    RECIPIENT = MESSAGE['To'] = args.email
    MESSAGE.preamble = 'Multipart message.\n'
    ATTACHMENT = MIMEText('Please find in attachement the report about unused Security groups over AWS regions. All the SG ids in the file are candidates for deletion')
    MESSAGE.attach(ATTACHMENT) 
    ATTACHMENT = MIMEApplication(open('all_sgs_deleted_all_regions.txt', 'rb').read())
    ATTACHMENT.add_header('Content-Disposition', 'attachment', filename='all_sgs_deleted_all_regions.txt')
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

print colored("RESULTS HAVE BEEN LOGGED IN all_sgs_deleted_all_regions.txt AND DETAILS HAVE BEEN SAVED IN details_sgs_deleted/ FOLDER","yellow")
# ORDER MESS BUT BE CARE IF YOU WANT TO USE THIS SCRIPT INSIDE A CRON (use /home/user) OR AWS LAMBDA (use /tmp/ dir)
timestr = time.strftime("%Y%m%d-%H%M")
try:
    os.system('mkdir details_sgs_deleted_%s;mv all_sgs_deleted_all_regions.txt all_sgs_deleted_all_regions_%s.txt;mv sg_detail_deleted_sg-*.txt details_sgs_deleted_%s/;rm -rf sgs_to_delete*.txt'%(timestr,timestr,timestr))
except Exception as e:
    print colored(e,"red") 
