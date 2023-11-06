import os
import shlex
import subprocess
from argparse import ArgumentParser

import requests
import yaml

CODE_PATHS = [
    "services",
    "example",
]

BRANCH_ENV = {"develop": "dev", "staging": "test", "master": "prod"}

ENV_NAMES = {
    "dev": "Dev",
    "test": "Test",
    "prod": "Prod",
}

ENV_REGIONS = {
    "dev": "ap-southeast-1",
    "test": "ap-southeast-1",
    "prod": "ap-southeast-1",
}

ENV_AWS_ACCOUNT_IDS = {
    "dev": "054647111382",
    "test": "072198228306",
    "prod": "381719257168",
}

ENV_ALLOWED_BRANCHES = {"dev": ["develop", "/.*_dev/"], "test": ["staging"], "prod": ["master"]}


def find_pr_changes(pr: str):
    """

    Parameters
    ----------
    pr

    Returns
    -------

    """

    project_name = os.environ.get("CIRCLE_PROJECT_REPONAME")
    github_token = os.environ.get("GITHUB_TOKEN")
    pr_number = pr.rsplit("/", 1)[-1]

    # get file changed in the PR
    pr_response_data = requests.get(
        url=f"https://api.github.com/repos/ElucidataInc/{project_name}/pulls/{pr_number}/files",
        headers={"Authorization": f"Bearer {github_token}"},
    ).json()

    return pr_response_data


def get_git_diff(branch_name: str):
    """

    Parameters
    ----------
    branch_name

    Returns
    -------

    """

    if branch_name.endswith("_dev"):
        os.system(
            f"git fetch origin develop -q && git checkout develop -q && git checkout {branch_name} -q"
        )
        git_change_set = set(
            subprocess.run(
                shlex.split(f'git diff --pretty="" --name-only develop {branch_name}'),
                stdout=subprocess.PIPE,
            )
            .stdout.decode("utf-8")
            .splitlines()
        )

    elif os.environ.get("CIRCLE_PULL_REQUEST"):  # check if it's a PR
        response = find_pr_changes(pr=os.environ.get("CIRCLE_PULL_REQUEST"))
        # get all the filenames affected in this PR
        git_change_set = set([item["filename"] for item in response])

    elif branch_name in BRANCH_ENV.keys():
        # os.system(f"git fetch origin {branch_name} -q && git checkout {branch_name} && git pull")
        git_change_set = set(
            subprocess.run(
                shlex.split(f"git diff --name-only HEAD HEAD~1"),
                stdout=subprocess.PIPE,
            )
            .stdout.decode("utf-8")
            .splitlines()
        )

    else:
        git_change_set = set(
            subprocess.run(
                shlex.split(
                    'git diff --pretty="" --name-only {}^ {}'.replace(
                        "{}", os.environ.get("CIRCLE_SHA1")
                    )
                ),
                stdout=subprocess.PIPE,
            )
            .stdout.decode("utf-8")
            .splitlines()
        )

    return git_change_set


def lambda_code_changes(branch_name: str):
    """

    Parameters
    ----------
    branch_name

    Returns
    -------

    """
    env = BRANCH_ENV.get(branch_name, "dev")
    lambda_router_path_mapping = dict(
        (k, v)
        for k, v in dict(os.environ).items()
        if len(k.split("_")) > 1 and env in k.split("_")[1].lower() and v.endswith(".py")
    )  # Filter out variables according to the AWS_ENV

    git_change_set = get_git_diff(branch_name=branch_name)

    lambda_package_mapping = dict()
    change_list = list()
    for k, v in lambda_router_path_mapping.items():
        result = subprocess.run(
            ["python3.9", "make_lambda_package.py", "-l", v], stdout=subprocess.PIPE
        )
        lambda_package_mapping[k] = set(result.stdout.decode("utf-8").splitlines())
        if lambda_package_mapping[k] & git_change_set:
            change_list.append(k)

    print(change_list)
    if change_list:
        with open(".circleci/workflow.yml", "r+") as file:
            workflow = yaml.safe_load(file)
            workflow["parameters"]["run-code-build-deploy"]["default"] = True
            jobs = workflow["workflows"]["code-build-deploy"]["jobs"]

            if branch_name == "master":
                jobs[0]["Code-Build"]["matrix"]["parameters"]["lambdahandler"] = change_list
                jobs[5]["Prod-Hold"]["matrix"]["parameters"]["lambdahandler"] = change_list
                jobs[6]["Prod-Code-Deploy"]["matrix"]["parameters"]["lambdahandler"] = change_list
            elif branch_name == "staging":
                jobs[0]["Code-Build"]["matrix"]["parameters"]["lambdahandler"] = change_list
                jobs[3]["Test-Hold"]["matrix"]["parameters"]["lambdahandler"] = change_list
                jobs[4]["Test-Code-Deploy"]["matrix"]["parameters"]["lambdahandler"] = change_list
            else:
                jobs[0]["Code-Build"]["matrix"]["parameters"]["lambdahandler"] = change_list
                jobs[1]["Dev-Hold"]["matrix"]["parameters"]["lambdahandler"] = change_list
                jobs[2]["Dev-Code-Deploy"]["matrix"]["parameters"]["lambdahandler"] = change_list
            file.seek(0)
            file.truncate()
            yaml.safe_dump(workflow, file, encoding="utf-8", sort_keys=False, indent=2, width=20000)


def add_ci_testing_params(services):
    """

    Parameters
    ----------
    services

    Returns
    -------

    """

    print("services", services)

    if isinstance(services, str):
        services = [services]

    # add service names to parameters for ci testing
    with open(".circleci/workflow.yml", "r+") as file:
        workflow = yaml.safe_load(file)
        workflow["parameters"]["run-ci-test-pipeline"]["default"] = True

        workflow["workflows"]["ci-test-pipeline"]["jobs"][0]["Code-Test"]["matrix"]["parameters"][
            "services"
        ] = services
        file.seek(0)
        file.truncate()
        yaml.safe_dump(workflow, file, encoding="utf-8", sort_keys=False, indent=2, width=20000)


def create_service_list():
    """
    This is triggered when branch is either staging or master

    Parameters
    ----------

    Returns
    -------

    """
    services = []
    for service in os.listdir("services/"):
        if service.endswith(".py"):
            continue

        # filter out services here if required for customization
        services.append(service)

    add_ci_testing_params(services=services)


def find_changes(branch: str, project_name: str = None, pr_number: int = None):
    """
    Finds the files that have been changed
    Parameters
    ----------
    project_name
    pr_number
    branch

    Returns
    -------

    """

    # setup layers for all services
    if branch in ("staging", "master"):
        return 1, ""

    github_token = os.environ.get("GITHUB_TOKEN")

    # get file changed in the PR
    pr_response_data = requests.get(
        url=f"https://api.github.com/repos/ElucidataInc/{project_name}/pulls/{pr_number}/files",
        headers={"Authorization": f"token {github_token}"},
    ).json()

    # for dev target branch
    for files in pr_response_data:
        # check if any changes made in commons
        if files["filename"].startswith("commons/"):
            # setup layers for all the services
            return 1, ""

        if files["filename"].startswith("services/"):
            return -1, files["filename"].split("/")[1]


def lambda_layer_changes(branch_name: str):
    """

    Parameters
    ----------
    branch_name

    Returns
    -------

    """
    env = BRANCH_ENV.get(branch_name, "dev")

    lambda_layer_req_path_mapping = dict(
        (k, v)
        for k, v in dict(os.environ).items()
        if len(k.split("_")) > 1
        and env in k.split("_")[1].lower()
        and v.endswith("requirements.txt")
    )  # Filter out variables according to the AWS_ENV

    git_change_list = list(get_git_diff(branch_name=branch_name))
    git_change_set = set(
        [
            file
            for file in git_change_list
            if file.endswith("requirements.txt")
            if len(file.split("/")) == 3
        ]
    )  # Filter out service level requirements

    change_list = list()

    for k, v in lambda_layer_req_path_mapping.items():
        if v in git_change_set:
            change_list.append(k)

    print(change_list)
    if change_list:
        with open(".circleci/workflow.yml", "r+") as file:
            workflow = yaml.safe_load(file)
            workflow["parameters"]["run-layer-build-deploy"]["default"] = True

            jobs = workflow["workflows"]["layer-build-deploy"]["jobs"]
            if branch_name == "master":
                jobs[0]["Layer-Build"]["matrix"]["parameters"]["requirements_file"] = change_list
                jobs[5]["Prod-Hold"]["matrix"]["parameters"]["requirements_file"] = change_list
                jobs[6]["Prod-Layer-Deploy"]["matrix"]["parameters"][
                    "requirements_file"
                ] = change_list
            elif branch_name == "staging":
                jobs[0]["Layer-Build"]["matrix"]["parameters"]["requirements_file"] = change_list
                jobs[3]["Test-Hold"]["matrix"]["parameters"]["requirements_file"] = change_list
                jobs[4]["Test-Layer-Deploy"]["matrix"]["parameters"][
                    "requirements_file"
                ] = change_list
            else:
                jobs[0]["Layer-Build"]["matrix"]["parameters"]["requirements_file"] = change_list
                jobs[1]["Dev-Hold"]["matrix"]["parameters"]["requirements_file"] = change_list
                jobs[2]["Dev-Layer-Deploy"]["matrix"]["parameters"][
                    "requirements_file"
                ] = change_list
            file.seek(0)
            file.truncate()
            yaml.safe_dump(workflow, file, encoding="utf-8", sort_keys=False, indent=2, width=20000)


def find_deployment_files(path: str) -> list[str]:
    deployment_files = []
    for root, _, files in os.walk(path):
        if "deployment.yaml" in files:
            deployment_files.append(os.path.join(root, "deployment.yaml"))
        if "deployment.yml" in files:
            deployment_files.append(os.path.join(root, "deployment.yml"))

    return deployment_files

def filter_unchanged_deployments(deployment: dict) -> bool:
    if not deployment.get("context"):
        return False

    return True

def ecs_deployment():
    branch_name = os.environ.get("CIRCLE_BRANCH")
    env = BRANCH_ENV.get(branch_name) or ("dev" if branch_name.endswith("_dev") else "dev")
    env_name = ENV_NAMES[env]
    region = ENV_REGIONS[env]
    aws_account_id = ENV_AWS_ACCOUNT_IDS[env]
    allowed_branches = ENV_ALLOWED_BRANCHES[env]

    print(get_git_diff(branch_name))

    if env is None:
        print("No deployment for this branch")
        return

    # search for deployment files in allowed code paths
    for path in CODE_PATHS:
        deployment_files = find_deployment_files(path)
        for deployment_file in deployment_files:
            with open(deployment_file, "r") as f:
                deployments = dict(yaml.safe_load(f)["resources"])

            # filter only ecs deployments
            ecs_deployments = list(filter(lambda x: x["type"] == "ecs", deployments.values()))
            print(ecs_deployments)

            ecs_deployments = list(filter(filter_unchanged_deployments, ecs_deployments))
            print(ecs_deployments)

            with open(".circleci/workflow.yml", "r+") as file:
                workflow = yaml.safe_load(file)
                workflow["parameters"]["run-ecs-build-deploy"]["default"] = True

                jobs = workflow["workflows"]["ecs-build-deploy"]["jobs"]

                for ecs_deployment in ecs_deployments:
                    ecs_cluster_name = str(ecs_deployment["cluster"]).replace("${DEPLOY_STAGE}", env)
                    ecs_service_name = str(ecs_deployment["service"]).replace("${DEPLOY_STAGE}", env)
                    dockerfile = ecs_deployment.get("dockerfile") or "Dockerfile"
                    context = ecs_deployment["context"]

                    ecr_image_name = (
                        str(ecs_deployment["image"])
                        .replace("${AWS_ACCOUNT_ID}", aws_account_id)
                        .replace("${AWS_REGION}", region)
                    )
                    # .replace("${DEPLOY_STAGE}", env)
                    ecr_image_tag = ecs_deployment.get("tag") or "latest"

                    workflow["jobs"][
                        f"Dev-ECS-Deploy-{ecs_cluster_name}-{ecs_service_name}"
                    ] = workflow["jobs"]["ecs-deploy"]

                    workflow["jobs"][f"Dev-ECS-Deploy-{ecs_cluster_name}-{ecs_service_name}"]["parameters"]["DOCKER_FILE"] = str(dockerfile)

                    jobs.append(
                        {
                            f"{env_name}-Hold-{ecs_cluster_name}-{ecs_service_name}": {
                                "name": f"{env_name}-Hold-{ecs_cluster_name}-{ecs_service_name}",
                                "type": "approval",
                                "filters": {"branches": {"only": allowed_branches}},
                            }
                        }
                    )

                    jobs.append(
                        {
                            f"{env_name}-ECS-Deploy-{ecs_cluster_name}-{ecs_service_name}": {
                                "name": f"{env_name}-ECS-Deploy-{ecs_cluster_name}-{ecs_service_name}",
                                "requires": 
                                    [f"{env_name}-Hold-{ecs_cluster_name}-{ecs_service_name}"],
                                "parameters": {
                                    "ECS_CLUSTER": ecs_cluster_name,
                                    "ECS_SERVICE": ecs_service_name,
                                    "PROFILE": env,
                                    "AWS_REGION": region,
                                    "DOCKER_FILE": dockerfile,
                                    "DOCKER_CONTEXT": context,
                                    "ECR_IMAGE": ecr_image_name,
                                    "DOCKER_TAG": ecr_image_tag,
                                },
                                "filters": {"branches": {"only": allowed_branches}},
                            }
                        }
                    )
                print(file)
                file.seek(0)
                file.truncate()

                yaml.safe_dump(
                    workflow, file, encoding="utf-8", sort_keys=False, indent=2, width=20000
                )
                # testfile = open("test.yml", "r+")

def main():
    """
    This utility creates the zip package for a given lambda handler python file.
    Returns
    -------

    """

    parser = ArgumentParser(
        description="""
                If a PR is raised, this function does integration testing for all the services affected
                It builds lambda layers and then tests requests on it
                """,
    )

    parser.add_argument(
        "-b",
        "--branch",
        help="Target branch to which this PR's changes will affect",
        default="develop",
    )

    args = parser.parse_args()

    branch_name = os.environ.get("CIRCLE_BRANCH")

    lambda_code_changes(branch_name)
    lambda_layer_changes(branch_name)
    ecs_deployment()

    # # check if it's a pull request
    # if os.environ.get("CIRCLE_PULL_REQUEST"):
    #     pr_number: int = int(os.environ.get("CIRCLE_PULL_REQUEST").split("/")[-1])
    #     project_name: str = os.environ.get("CIRCLE_PROJECT_REPONAME")

    #     # build layers for the affected services
    #     mode, service = find_changes(
    #         project_name=project_name, pr_number=pr_number, branch=args.branch
    #     )

    #     print(mode, service)
    #     if mode == -1:
    #         add_ci_testing_params(services=service)

    #     else:
    #         create_service_list()


if __name__ == "__main__":
    main()
