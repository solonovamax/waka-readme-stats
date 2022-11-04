"""
Readme Development Metrics With waka time progress
"""
import base64
import datetime
import json
import os
import re
import traceback
from string import Template
from urllib.parse import quote

import humanize
import math
import pytz
import requests
from dotenv import load_dotenv
from github import Github, InputGitAuthor
from pytz import timezone

from loc import LinesOfCode

load_dotenv()

START_COMMENT = '<!--START_SECTION:waka-->'
END_COMMENT = '<!--END_SECTION:waka-->'
listReg = f"{START_COMMENT}[\\s\\S]+{END_COMMENT}"

waka_key = os.getenv('INPUT_WAKATIME_API_KEY')
waka_url = os.getenv('INPUT_WAKATIME_URL')
githubToken = os.getenv('INPUT_GH_TOKEN')
showTimeZone = os.getenv('INPUT_SHOW_TIMEZONE')
showProjects = os.getenv('INPUT_SHOW_PROJECTS')
showEditors = os.getenv('INPUT_SHOW_EDITORS')
showOs = os.getenv('INPUT_SHOW_OS')
showCommit = os.getenv('INPUT_SHOW_COMMIT')
showLanguage = os.getenv('INPUT_SHOW_LANGUAGE')
show_loc = os.getenv('INPUT_SHOW_LINES_OF_CODE')
show_days_of_week = os.getenv('INPUT_SHOW_DAYS_OF_WEEK')
showLanguagePerRepo = os.getenv('INPUT_SHOW_LANGUAGE_PER_REPO')
showLocChart = os.getenv('INPUT_SHOW_LOC_CHART')
show_profile_view = os.getenv('INPUT_SHOW_PROFILE_VIEWS')
show_short_info = os.getenv('INPUT_SHOW_SHORT_INFO')
locale = os.getenv('INPUT_LOCALE')
commit_by_me = os.getenv('INPUT_COMMIT_BY_ME')
ignored_repos_name = str(os.getenv('INPUT_IGNORED_REPOS') or '').replace(' ', '').split(',')
show_updated_date = os.getenv('INPUT_SHOW_UPDATED_DATE')
commit_message = os.getenv('INPUT_COMMIT_MESSAGE')
show_total_code_time = os.getenv('INPUT_SHOW_TOTAL_CODE_TIME')
show_waka_stats = 'y'
# The GraphQL query to get commit data.
userInfoQuery = """
# noinspection GraphQLUnresolvedReference
query {
    viewer {
        login
        email
        id
    }
}
"""
createContributedRepoQuery = Template("""
# noinspection GraphQLUnresolvedReference
query {
    user(login: "$username") {
        repositoriesContributedTo(last: 100, includeUserRepositories: true) {
            nodes {
                isFork
                name
                owner {
                    login
                }
            }
        }
    }
}
""")
createCommittedDateQuery = Template("""
# noinspection GraphQLUnresolvedReference
query {
    repository(owner: "$owner", name: "$name") {
        defaultBranchRef {
            target {
                ... on Commit {
                    history(first: 100, author: { id: "$id" }) {
                        edges {
                            node {
                                committedDate
                            }
                        }
                    }
                }
            }
        }
    }
}
""")

get_loc_url = Template("""/repos/$owner/$repo/stats/code_frequency""")
get_profile_view = Template("""/repos/$owner/$repo/traffic/views?per=week""")
get_profile_traffic = Template("""/repos/$owner/$repo/traffic/popular/referrers""")
truthy = ['true', '1', 't', 'y', 'yes']


def run_v3_api(query):
    request = requests.get('https://api.github.com' + query, headers=headers)
    if request.status_code == 200:
        return request.json()
    else:
        raise Exception(
            "Query failed to run by returning code of {}. {},... {}".format(request.status_code, query,
                                                                            str(request.json())))


repositoryListQuery = Template("""
# noinspection GraphQLUnresolvedReference
query {
    user(login: "$username") {
        repositories(
            orderBy: {field: CREATED_AT, direction: ASC},
            last: 100,
            affiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER],
            isFork: false
        ) {
            totalCount
            edges {
                node {
                    object(expression: "master") {
                        ... on Commit {
                            history (author: { id: "$id" }){
                                totalCount
                            }
                        }
                    }
                    primaryLanguage {
                        color
                        name
                        id
                    }
                    stargazers {
                        totalCount
                    }
                    collaborators {
                        totalCount
                    }
                    createdAt
                    name
                    owner {
                        id
                        login
                    }
                    nameWithOwner
                }
            }
        }
        location
        createdAt
        name
    }
}
""")


def millify(n):
    # noinspection SpellCheckingInspection,GrazieInspection
    millnames = ['', ' Thousand', ' Million', ' Billion', ' Trillion']
    n = float(n)
    # noinspection SpellCheckingInspection
    millidx = max(
        0,
        min(
            len(millnames) - 1,
            int(math.floor(0 if n == 0 else math.log10(abs(n)) / 3))
        )
    )

    return '{:.0f}{}'.format(n / 10 ** (3 * millidx), millnames[millidx])


def run_query(query):
    request = requests.post('https://api.github.com/graphql', json={'query': query}, headers=headers)
    if request.status_code == 200:
        return request.json()
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))


def make_graph(percent: float):
    """Make progress graph from API graph"""
    done_block = '█'
    empty_block = '░'
    pc_rnd = round(percent)
    return f"{done_block * int(pc_rnd / 4)}{empty_block * int(25 - int(pc_rnd / 4))}"


def make_list(commit_data: list):
    """Make List"""
    data_list = []
    for l in commit_data[:5]:
        ln = len(l['name'])
        ln_text = len(l['text'])
        op = f"{l['name'][:25]}{' ' * (25 - ln)}{l['text']}{' ' * (20 - ln_text)}{make_graph(l['percent'])}   {l['percent']}%"
        data_list.append(op)
    return ' \n'.join(data_list)


def make_commit_list(commit_data: list):
    """Make List"""
    data_list = []
    for l in commit_data[:7]:
        ln = len(l['name'])
        ln_text = len(l['text'])
        op = f"{l['name']}{' ' * (13 - ln)}{l['text']}{' ' * (15 - ln_text)}{make_graph(l['percent'])}   {l['percent']}%"
        data_list.append(op)
    return ' \n'.join(data_list)


def generate_commit_list(tz):
    string = ''
    result = run_query(userInfoQuery)  # Execute the query
    commit_user_username = result["data"]["viewer"]["login"]
    commit_user_id = result["data"]["viewer"]["id"]
    # print("user {}".format(username))

    result = run_query(createContributedRepoQuery.substitute(username=commit_user_username))
    nodes = result["data"]["user"]["repositoriesContributedTo"]["nodes"]
    repos = [d for d in nodes if d['isFork'] is False]

    morning = 0  # 6 - 12
    daytime = 0  # 12 - 18
    evening = 0  # 18 - 24
    night = 0  # 0 - 6

    monday_commits = 0
    tuesday_commits = 0
    wednesday_commits = 0
    thursday_commits = 0
    friday_commits = 0
    saturday_commits = 0
    sunday_commits = 0

    for repository in repos:
        result = run_query(
            createCommittedDateQuery.substitute(owner=repository["owner"]["login"], name=repository["name"], id=commit_user_id))
        try:
            committed_dates = result["data"]["repository"]["defaultBranchRef"]["target"]["history"]["edges"]
            for committedDate in committed_dates:
                date = datetime.datetime.strptime(committedDate["node"]["committedDate"],
                                                  "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc).astimezone(
                    timezone(tz))
                hour = date.hour
                weekday = date.strftime('%A')
                if 6 <= hour < 12:
                    morning += 1
                if 12 <= hour < 18:
                    daytime += 1
                if 18 <= hour < 24:
                    evening += 1
                if 0 <= hour < 6:
                    night += 1

                if weekday == "Monday":
                    monday_commits += 1
                if weekday == "Tuesday":
                    tuesday_commits += 1
                if weekday == "Wednesday":
                    wednesday_commits += 1
                if weekday == "Thursday":
                    thursday_commits += 1
                if weekday == "Friday":
                    friday_commits += 1
                if weekday == "Saturday":
                    saturday_commits += 1
                if weekday == "Sunday":
                    sunday_commits += 1
        except Exception as ex:
            if str(ex) != "'NoneType' object is not subscriptable":
                print("Exception occurred " + str(ex))

    total_commits = morning + daytime + evening + night
    sum_week = sunday_commits + monday_commits + tuesday_commits + friday_commits + saturday_commits + wednesday_commits + thursday_commits
    title = translate['When I work']
    subtitle = translate['I am an Early'] if morning + daytime >= evening + night else translate['I am a Night']
    one_day = [
        {"name": translate['Morning'], "text": str(morning) + " commits",
         "percent": round((morning / total_commits) * 100, 2)},
        {"name": translate['Daytime'], "text": str(daytime) + " commits",
         "percent": round((daytime / total_commits) * 100, 2)},
        {"name": translate['Evening'], "text": str(evening) + " commits",
         "percent": round((evening / total_commits) * 100, 2)},
        {"name": translate['Night'], "text": str(night) + " commits",
         "percent": round((night / total_commits) * 100, 2)},
    ]
    commits_by_day = [
        {"name": translate['Monday'], "text": str(monday_commits) + " commits", "percent": round((monday_commits / sum_week) * 100, 2)},
        {"name": translate['Tuesday'], "text": str(tuesday_commits) + " commits",
         "percent": round((tuesday_commits / sum_week) * 100, 2)},
        {"name": translate['Wednesday'], "text": str(wednesday_commits) + " commits",
         "percent": round((wednesday_commits / sum_week) * 100, 2)},
        {"name": translate['Thursday'], "text": str(thursday_commits) + " commits",
         "percent": round((thursday_commits / sum_week) * 100, 2)},
        {"name": translate['Friday'], "text": str(friday_commits) + " commits", "percent": round((friday_commits / sum_week) * 100, 2)},
        {"name": translate['Saturday'], "text": str(saturday_commits) + " commits",
         "percent": round((saturday_commits / sum_week) * 100, 2)},
        {"name": translate['Sunday'], "text": str(sunday_commits) + " commits", "percent": round((sunday_commits / sum_week) * 100, 2)},
    ]

    string = string + '**' + title + '** \n\n' + '```text\n' + subtitle + ': \n' + make_commit_list(one_day) + '\n\n'

    if show_days_of_week.lower() in truthy:
        max_element = {
            'percent': 0
        }

        for day in commits_by_day:
            if day['percent'] > max_element['percent']:
                max_element = day
        days_title = translate['I am Most Productive on'] % max_element['name']
        string = string + '\n' + days_title + ': \n' + make_commit_list(commits_by_day) + '\n\n```\n'
    else:
        string = string + '```\n'

    return string


def get_waka_time_stats():
    stats = ''
    request = requests.get(
        f"https://{waka_url}/v1/users/current/stats/last_30_days?api_key={waka_key}")
    current_user_request = requests.get(
        f"https://{waka_url}/v1/users/current?api_key={waka_key}"
    )
    no_activity = translate["No Activity Tracked This Week"]

    if request.status_code == 401:
        print("Error With WAKA time API returned " + str(request.status_code) + " Response " + str(request.json()))
    else:
        empty = True
        request_data = request.json()
        current_user_data = current_user_request.json()
        if showCommit.lower() in truthy:
            empty = False
            stats = stats + generate_commit_list(tz=current_user_data['data']['timezone']) + '\n\n'

        stats += '**' + translate['This Week I Spend My Time On'] + '** \n\n'
        stats += '```text\n'
        if showTimeZone.lower() in truthy:
            empty = False
            user_timezone = current_user_data['data']['timezone']
            stats += translate['Timezone'] + ': ' + user_timezone + '\n\n'

        if showLanguage.lower() in truthy:
            empty = False
            if len(request_data['data']['languages']) == 0:
                lang_list = no_activity
            else:
                lang_list = make_list(request_data['data']['languages'])
            stats += translate['Languages'] + ': \n' + lang_list + '\n\n'

        if showEditors.lower() in truthy:
            empty = False
            if len(request_data['data']['editors']) == 0:
                edit_list = no_activity
            else:
                edit_list = make_list(request_data['data']['editors'])
            stats += translate['Editors'] + ': \n' + edit_list + '\n\n'

        if showProjects.lower() in truthy:
            empty = False
            if len(request_data['data']['projects']) == 0:
                project_list = no_activity
            else:
                # Re-order the project list by percentage
                request_data['data']['projects'] = sorted(request_data['data']['projects'], key=lambda x: x["percent"], reverse=True)
                project_list = make_list(request_data['data']['projects'])
            stats += translate['Projects'] + ': \n' + project_list + '\n\n'

        if showOs.lower() in truthy:
            empty = False
            if len(request_data['data']['operating_systems']) == 0:
                os_list = no_activity
            else:
                os_list = make_list(request_data['data']['operating_systems'])
            stats += translate['operating system'] + ': \n' + os_list + '\n\n'

        stats += '```\n\n'
        if empty:
            return ""
    return stats


def generate_language_per_repo(result):
    language_count = {}
    total = 0
    for repo_result in result['data']['user']['repositories']['edges']:
        if repo_result['node']['primaryLanguage'] is None:
            continue
        language = repo_result['node']['primaryLanguage']['name']
        color_code = repo_result['node']['primaryLanguage']['color']
        total += 1
        if language not in language_count.keys():
            language_count[language] = {}
            language_count[language]['count'] = 1
        else:
            language_count[language]['count'] = language_count[language]['count'] + 1
        language_count[language]['color'] = color_code
    language_data = []
    sorted_labels = list(language_count.keys())
    sorted_labels.sort(key=lambda x: language_count[x]['count'], reverse=True)
    most_language_repo = sorted_labels[0]
    for label in sorted_labels:
        percent = round(language_count[label]['count'] / total * 100, 2)
        extension = " repos"
        if language_count[label]['count'] == 1:
            extension = " repo"
        language_data.append({
            "name": label,
            "text": str(language_count[label]['count']) + extension,
            "percent": percent
        })

    title = translate['I Mostly Code in'] % most_language_repo
    return '**' + title + '** \n\n' + '```text\n' + make_list(language_data) + '\n\n```\n'


def get_yearly_data():
    repository_list = run_query(repositoryListQuery.substitute(username=username, id=user_id))
    loc = LinesOfCode(user_id, username, githubToken, repository_list, ignored_repos_name)
    yearly_data = loc.calculateLoc()
    if showLocChart.lower() in truthy:
        loc.plotLoc(yearly_data)
    return yearly_data


def get_line_of_code():
    repository_list = run_query(repositoryListQuery.substitute(username=username, id=user_id))
    loc = LinesOfCode(user_id, username, githubToken, repository_list, ignored_repos_name)
    yearly_data = loc.calculateLoc()
    total_loc = sum(
        [yearly_data[year][quarter][lang] for year in yearly_data for quarter in yearly_data[year] for lang in
         yearly_data[year][quarter]])
    return millify(int(total_loc))


def get_short_info(github):
    string = '**' + translate['My GitHub Data'] + '**\n\n'
    user_info = github.get_user()
    if user_info.disk_usage is None:
        disk_usage = humanize.naturalsize(0)
        print("Please add new GitHub personal access token with user permission")
    else:
        disk_usage = humanize.naturalsize(user_info.disk_usage)
    request = requests.get('https://github-contributions.now.sh/api/v1/' + user_info.login)
    if request.status_code == 200:
        request_data = request.json()
        total = request_data['years'][0]['total']
        year = request_data['years'][0]['year']
        string += f"> {translate['Contributions in the year'] % (humanize.intcomma(total), year)}\n> \n"

    string += f"> {translate['Used in GitHubs Storage'] % disk_usage}\n> \n"
    is_hireable = user_info.hireable
    public_repo = user_info.public_repos
    private_repo = user_info.owned_private_repos
    if private_repo is None:
        private_repo = 0
    if is_hireable:
        string += f"> {translate['Opted to Hire']}\n> \n"
    else:
        string += f"> {translate['Not Opted to Hire']}\n> \n"

    string += '> '
    string += f"{translate['public repositories'] % public_repo}\n> \n" \
        if public_repo != 1 else f"{translate['public repository'] % public_repo}\n> \n"
    string += '> '
    string += f"{translate['private repositories'] % private_repo}\n> \n" \
        if private_repo != 1 else f"{translate['private repository'] % private_repo}\n> \n"

    return string


def get_stats(github):
    """Gets API data and returns markdown progress"""

    stats = ''
    repository_list = run_query(repositoryListQuery.substitute(username=username, id=user_id))

    # if show_loc.lower() in truthy or showLocChart.lower() in truthy:
    #     # This condition is written to calculate the lines of code because it is heavy process soo needs to be calculate once this will
    #     # reduce the execution time
    #     yearly_data = get_yearly_data()

    if show_total_code_time.lower() in truthy:
        request = requests.get(
            f"https://{waka_url}/v1/users/current/all_time_since_today?api_key={waka_key}")
        if request.status_code == 401:
            print("Error With WAKA time API returned " + str(request.status_code) + " Response " + str(request.json()))
        elif "text" not in request.json()["data"]:
            print("User stats are calculating. Try again later.")
        else:
            request_data = request.json()
            stats += '![Code Time](https://img.shields.io/badge/' + quote(str("Code Time")) + '-' + quote(str(request_data['data']['text'])) \
                     + '-blue?style=for-the-badge)\n\n'

    if show_profile_view.lower() in truthy:
        request_data = run_v3_api(get_profile_view.substitute(owner=username, repo=username))
        stats += '![Profile Views](https://img.shields.io/badge/' + quote(str(translate['Profile Views'])) + '-' + str(
            request_data['count']) + '-blue?style=for-the-badge)\n\n'

    if show_loc.lower() in truthy:
        stats += '![Lines of code](https://img.shields.io/badge/' + quote(
            str(translate['From Hello World I have written'])) + '-' + quote(
            str(get_line_of_code())) + '%20' + quote(str(translate['Lines of code'])) + '-blue?style=for-the-badge)\n\n'

    if show_short_info.lower() in truthy:
        stats += get_short_info(github)

    if show_waka_stats.lower() in truthy:
        stats += get_waka_time_stats()

    if showLanguagePerRepo.lower() in truthy:
        stats = stats + generate_language_per_repo(repository_list) + '\n\n'

    if showLocChart.lower() in truthy:
        stats += '**' + translate['Timeline'] + '**\n\n'
        branch_name = github.get_repo(f'{username}/{username}').default_branch
        stats += f"![Chart not found](https://raw.githubusercontent.com/{username}/{username}/{branch_name}/charts/bar_graph.png)\n\n"

    if show_updated_date.lower() in truthy:
        now = datetime.datetime.utcnow()
        d1 = now.strftime("%d/%m/%Y %H:%M:%S")
        stats = stats + "\n Last Updated on " + d1 + " UTC"

    return stats


# def star_me():
# requests.put("https://api.github.com/user/starred/anmol098/waka-readme-stats", headers=headers)

def decode_readme(decode_data: str):
    """Decode the contents of old readme"""
    decoded_bytes = base64.b64decode(decode_data)
    return str(decoded_bytes, 'utf-8')


def generate_new_readme(stats: str, old_readme: str):
    """Generate a new Readme.md"""
    stats_in_readme = f"{START_COMMENT}\n{stats}\n{END_COMMENT}"
    return re.sub(listReg, stats_in_readme, old_readme)


if __name__ == '__main__':
    try:
        start_time = datetime.datetime.now().timestamp() * 1000
        if githubToken is None:
            raise Exception('Token not available')
        g = Github(githubToken)
        headers = {"Authorization": "Bearer " + githubToken}
        user_data = run_query(userInfoQuery)  # Execute the query
        username = user_data["data"]["viewer"]["login"]
        user_id = user_data["data"]["viewer"]["id"]
        emails_user = run_v3_api("/user/emails")  # Execute the api
        email = emails_user[0]['email']
        print("Username " + username)
        repo = g.get_repo(f"{username}/{username}")
        contents = repo.get_readme()
        try:
            with open(os.path.join(os.path.dirname(__file__), 'translation.json'), encoding='utf-8') as config_file:
                data = json.load(config_file)
            translate = data[locale]
        except Exception as e:
            print("Cannot find the Locale choosing default to english")
            translate = data['en']
        waka_stats = get_stats(g)
        # star_me()
        readme = decode_readme(contents.content)
        new_readme = generate_new_readme(stats=waka_stats, old_readme=readme)
        if commit_by_me.lower() in truthy:
            committer = InputGitAuthor(username, email)
        else:
            committer = InputGitAuthor('readme-bot', '41898282+github-actions[bot]@users.noreply.github.com')
        if new_readme != readme:
            try:
                repo.update_file(path=contents.path, message=commit_message,
                                 content=new_readme, sha=contents.sha, branch='master',
                                 committer=committer)
            except:
                repo.update_file(path=contents.path, message=commit_message,
                                 content=new_readme, sha=contents.sha, branch='main',
                                 committer=committer)
            print("Readme updated")
        end_time = datetime.datetime.now().timestamp() * 1000
        print("Program processed in {} miliseconds.".format(round(end_time - start_time, 0)))
    except Exception as e:
        traceback.print_exc()
        print("Exception Occurred " + str(e))
