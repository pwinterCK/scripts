#!/usr/bin/env python
## PWIPWI 13/11/2018
import boto3
import os
import argparse 

parser = argparse.ArgumentParser(description="THIS SCRIPT WILL UPLOAD ALL THE VTT FILES INSIDE THE GIVEN PATH TO S3 SA-EAST-1 WITH CONTENT TYPE text/vtt AND PUBLIC READ FOR ACL / DESTINATION BUCKET https://s3.console.aws.amazon.com/s3/buckets/alltypes-assessment/media/activities/subtitles/?region=sa-east-1&tab=overview") 

parser.add_argument("-p", "--path", type=str,help="Specify the folder path where the VTT files are located on your local machine; /home/pwinter/subtitles_to_S3/") 
args=parser.parse_args() 

if not args.path:
    print ("-p arg should be specified or try -h")
    exit() 
else: 
    s3 = boto3.resource('s3','sa-east-1')
    bucket = s3.Bucket('SET BUCKET NAME HERE')
    mydir = args.path
    for root, dirs, files in os.walk(mydir):
        for file in files:
            if file.endswith('.vtt'):
                try:
                    bucket.upload_file(mydir+file, 'media/activities/subtitles/'+file, ExtraArgs={'ContentType': 'text/vtt', 'ACL':'public-read'})
                    my_object = bucket.Object('media/activities/subtitles/'+file)
                    print(str(file) + " has been uploaded to S3 successfully")
                except Exception as e:
                    print (e, "MAYBE TRY TO ADD A / AT THE END OF YOUR PATH ARG")
            else:
                print("YOU TRYING TO UPLOAD SOMETHING ELSE THAN SUBTITLES: SKIPPING " + str(file))  
