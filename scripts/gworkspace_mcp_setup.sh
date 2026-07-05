#!/bin/bash

# Enable Google Workspace APIs for MCP
PROJECT_ID=${1}

if [ -z "${PROJECT_ID}" ]; then
    echo "PROJECT_ID is required"
    exit 1
fi

gcloud services enable \
    gmail.googleapis.com \
    gmailmcp.googleapis.com \
    calendar-json.googleapis.com \
    calendarmcp.googleapis.com \
    drive.googleapis.com \
    drivemcp.googleapis.com \
        --project=${PROJECT_ID}
if [ $? -ne 0 ]; then
    echo "Failed to enable Google Workspace APIs"
    exit 1
fi

echo "Google Workspace APIs enabled for project ${PROJECT_ID}"
echo "Please follow the steps below to complete the setup:"
echo "1. Setup Branding - https://console.cloud.google.com/auth/branding"
echo "2. Add Data Access Scopes - https://console.cloud.google.com/auth/scopes"
echo "   https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.compose,https://www.googleapis.com/auth/calendar.calendarlist.readonly,https://www.googleapis.com/auth/calendar.events.freebusy,https://www.googleapis.com/auth/calendar.events.readonly,https://www.googleapis.com/auth/drive.readonly,https://www.googleapis.com/auth/drive.file"
echo "3. Create OAuth Client ID - https://console.cloud.google.com/apis/credentials"
echo "   * Web Application"
echo "   * Redirect URI - https://antigravity.google/oauth-callback"
