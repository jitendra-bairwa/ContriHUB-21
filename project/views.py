from django.shortcuts import HttpResponseRedirect, reverse
from contrihub.settings import AVAILABLE_PROJECTS, LABEL_MENTOR, LABEL_LEVEL, LABEL_POINTS, DEPENDABOT_LOGIN, \
    LABEL_RESTRICTED, DEFAULT_FREE_POINTS, DEFAULT_VERY_EASY_POINTS, DEFAULT_EASY_POINTS, DEFAULT_MEDIUM_POINTS, DEFAULT_HARD_POINTS
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth import get_user_model
from .models import Project, Issue
from helper import complete_profile_required, fetch_all_issues
from config import APIS, URIS
User = get_user_model()


@user_passes_test(lambda u: u.userprofile.role == u.userprofile.ADMIN)
@complete_profile_required
def populate_projects(request):
    """
    Used to Populate Projects in Local Database. Creates entries based on project names present in AVAILABLE_PROJECTS
    config variable in settings.py
    :param request:
    :return:
    """
    api_uri = APIS['api_contrihub']
    html_uri = URIS['uri_html']
    print(AVAILABLE_PROJECTS)
    for project_name in AVAILABLE_PROJECTS:
        project_qs = Project.objects.filter(name=project_name)
        if not project_qs:
            api_url = f"{api_uri}{project_name}"
            html_url = f"{html_uri}{project_name}"
            Project.objects.create(
                name=project_name,
                api_url=api_url,
                html_url=html_url
            )

    return HttpResponseRedirect(reverse('home'))


@user_passes_test(lambda u: u.userprofile.role == u.userprofile.ADMIN)
@complete_profile_required
def populate_issues(request):
    """
    Used to Populate Issues in Local Database. It fetches Issues from Github using Github API.
    :param request:
    :return:
    """
    project_qs = Project.objects.all()

    social = request.user.social_auth.get(provider='github')
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {social.extra_data['access_token']}",  # Authentication
    }
    uri = APIS['api_contrihub']

    for project in project_qs:
        print("PROJECT: ", project.name)
        issues_dict = fetch_all_issues(uri, project.name, headers)
        issues = issues_dict['data']
        print("COUNT: ", len(issues))
        for issue in issues:
            # TODO: Can be given as ISSUE
            if issue['user']['login'] == DEPENDABOT_LOGIN:  # Ignoring issues created by Dependabot
                continue
            if issue.get('pull_request') is not None:  # this issue is actually a PR.
                # Source: https://docs.github.com/en/rest/reference/issues#list-repository-issues
                print("This issue is a actually a PR")
                continue
            title, number = issue['title'], issue['number']
            mentor_name, level, points, is_restricted = parse_labels(labels=issue['labels'])

            if mentor_name and level:  # If mentor name and level labels are present in issue
                api_url, html_url = issue['url'], issue['html_url']
                issue_qs = Issue.objects.filter(number=number, project=project)
                # print("I: ", number, title, mentor_name, level)
                if issue_qs:  # Update if already present
                    db_issue = issue_qs.first()
                    db_issue.title = title
                    db_issue.level = level
                    db_issue.points = points
                    db_issue.is_restricted = is_restricted
                else:  # Else Create New
                    db_issue = Issue(
                        number=number,
                        title=title,
                        api_url=api_url,
                        html_url=html_url,
                        project=project,
                        level=level,
                        points=points,
                        is_restricted=is_restricted
                    )

                # print(db_issue)
                try:
                    mentor = User.objects.get(username=mentor_name)
                    db_issue.mentor = mentor
                except User.DoesNotExist:
                    pass

                db_issue.save()

    return HttpResponseRedirect(reverse('home'))


def parse_labels(labels):
    mentor, level, points, is_restricted = None, None, 0, False
    for label in labels:

        if str(label["description"]).lower() == LABEL_MENTOR:  # Parsing Mentor
            mentor = parse_mentor(label["name"])

        if str(label["description"]).lower() == LABEL_LEVEL:  # Parsing Level
            level, points = parse_level(label["name"])  # Fetching Level and it's default point

        if str(label["description"]).lower() == LABEL_POINTS:  # Parsing Points
            points = parse_points(label["name"])  # Consider Custom points if provided

        if str(label["name"]).lower() == LABEL_RESTRICTED:  # Parsing Is Restricted
            is_restricted = True

    return mentor, level, points, is_restricted


def parse_level(level):
    level = str(level).lower()
    levels_read = (Issue.FREE_READ, Issue.VERY_EASY_READ, Issue.EASY_READ, Issue.MEDIUM_READ, Issue.HARD_READ)
    levels = (Issue.FREE, Issue.VERY_EASY, Issue.EASY, Issue.MEDIUM, Issue.HARD)
    default_points = (DEFAULT_FREE_POINTS, DEFAULT_VERY_EASY_POINTS, DEFAULT_EASY_POINTS, DEFAULT_MEDIUM_POINTS, DEFAULT_HARD_POINTS)

    for lev, read, pts in zip(levels, levels_read, default_points):
        if level == str(read).lower():
            return lev, pts

    return Issue.EASY, DEFAULT_EASY_POINTS  # Default FallBack


def parse_mentor(mentor):
    return str(mentor).lower()


def parse_points(points):
    points = str(points)

    if points.isnumeric():
        return int(float(points))

    return 0  # Default FallBack
