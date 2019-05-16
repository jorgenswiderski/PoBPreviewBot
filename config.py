username = "aggixxTest"
#subreddits = ["test", "pobPreviewTest"]
subreddits = ["test", "pobPreviewTest", "funny"]

submission_parse_interval = 30
comment_parse_interval = 10
initial_pull_count = 50
min_pull_count = 5
pull_count_tracking_window = 10
max_pull_count = 200

# Max amount of time to go back and look for comments/submissions when starting bot
backlog_time_limit = 86400 * 3 # 3 days

deletion_check_interval_rng = 0.01

praw_error_wait_time = 5
urllib_error_wait_time = 60

preserve_comments_after = 15552000 # 180 days


BOT_FOOTER = "[^Path ^of ^Building](https://github.com/Openarl/PathOfBuilding) ^| ^This ^reply ^automatically ^updates ^based ^on ^its ^parent ^comment. ^| ^[Feedback?](https://www.reddit.com/r/PoBPreviewBot/)"
BOT_INTRO = "Hi there! I'm a bot that replies to [Path of Building](https://github.com/Openarl/PathOfBuilding) pastebins with a short summary of the build [like this](https://i.imgur.com/Ee9Sbo1.png)! Just include a link to any Path of Building pastebin in your comment or submission and I'll automatically respond."