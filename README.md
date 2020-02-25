# Dev Environment

Clone this repo. 
Define these variables in your bash profile:
* `WORK_HOME` - where do you clone work repos
* `WORK_ORG` - github org you generally clone from
* `WORK_WIFI_CIDR` - CIDR to scan for wireless devices at the office, **if you have permission**
* `GITHUB_USERNAME` - github user
* `GITHUB_USERS` - other github users who work you may pull seperated by commas
* `DEV_HOME` - top level directory for dev work
* `DEV_ENV_HOME` - directory you cloned this to

Add a `source $DEV_ENV_HOME/.bash_profile` to your bash profile.