import sys
import subprocess
import os


def list_dumps(path):
    remote_path = path.split('/')[-1]
    dump_list = subprocess.Popen("aws s3 ls s3://holserver-backups/game-dynamo/us-west-2/" + remote_path + "/"
                                 "| awk '{print $2}' "
                                 "| sed 's/\/$//'", shell=True, stdout=subprocess.PIPE).stdout.read()
    return dump_list


def check_dump(path, dump_date):
    print("Checking if " + dump_date + " exists")
    dump_list = list_dumps(path).split("\n")
    for d in dump_list:
        # print d.split(".")[0]
        if d.split(".")[0] == dump_date:
            print("Found " + d)
            return d


def get_dump(path, dump_date):
    print("Syncing " + dump_date)
    remote_path = path.split('/')[-1]
    dump_filename = subprocess.Popen("aws s3 ls s3://holserver-backups/game-dynamo/us-west-2/" + remote_path + "/"
                                     + dump_date + "/ | awk '{ print $4 }'",
                                     shell=True, stdout=subprocess.PIPE).stdout.read()[:-1]
    print("Writing " + dump_filename)  # does this have a newline on the end by mistake?
    subprocess.Popen("aws s3 sync s3://holserver-backups/game-dynamo/us-west-2/" + remote_path + "/"
                     + dump_date + "/"
                     + " " + dynamodump_path + "/dumps/", shell=True, stdout=subprocess.PIPE).stdout.read()

    return dump_filename


def sanitize(path, dump_filename, player_id):
    print("Sanitizing output for dumps/" + dump_filename)

    out = subprocess.Popen("grep --color=none " + player_id + " " + dynamodump_path + "/dumps/" + dump_filename +
                           " | sed -e 's/$/}/' -e $'s/\\x02/,\"/g' -e $'s/\\x03/\":/g' -e 's/^/{\"/' "
                           " | sed -e ':a' -e 'N' -e '$!ba' -e 's/\\n/<>/g' | tr '<' ',' | tr '>' '\n' | "
                           "sed -e 's/\"n\"/\"N\"/g' -e 's/\"s\"/\"S\"/g'",
                           shell=True, stdout=subprocess.PIPE).stdout.read()

    if len(out) == 0:  # if the above processing resulted in an empty result, try this one. not proud of this solution.
        out = subprocess.Popen("grep --color=none " + player_id + " " + dynamodump_path + "/dumps/" + dump_filename +
                               " | sed -e 's/$/}/' -e $'s/\\x02/,\"/g' -e $'s/\\x03/\":/g' -e 's/^/{\"/'"
                               " | sed -e 's/\"n\"/\"N\"/g' -e 's/\"s\"/\"S\"/g'",
                               shell=True, stdout=subprocess.PIPE).stdout.read()

    out = "{\"Items\":[" + out + "]}"
    out = out.replace("\"s\"", "\"S\"")  # this seems unnecessary but I included it just in case
    out = out.replace("\"n\"", "\"N\"")  # this seems unnecessary but I included it just in case
    out = out.replace("{\"{\"", "{\"")  # I don't know why this happened but whatever let's clean it up
    out = out.replace("\"}}}", "\"}}")  # I don't know why this happened but whatever let's clean it up
    fo = open(path + "/data/" + dump_filename + ".json", 'w')
    fo.write(out)


def do_docker_dynamodump(path):
    docker_path = path.split('/')[-1]
    print("Running dynamodump.py inside docker container for " + docker_path)
    dout = subprocess.Popen("docker run --rm -ti -v ~/mastermind/holserver:/opt/mastermind/holserver"
                            " -v " + dynamodump_path + ":/opt/dynamodump"
                            " --link local_dynamo:dynamo_host mastermind/holserver"
                            " bash -c \"cd /opt/dynamodump/; pwd; python dynamodump.py -m restore -r local --dataOnly "
                            "-s " + docker_path + " --host dynamo_host --port 8000 "
                            "--accessKey anything --secretKey anything --log DEBUG\"",
                            shell=True, stdout=subprocess.PIPE).stdout.read()
    print(dout)


def verify_paths():
    paths_set = True
    if not os.getenv('DYNAMODUMP_INSTALL_PATH'):
        print("ERROR: DYNAMODUMP_INSTALL_PATH not set!")
        paths_set = False

    if not os.path.exists(dynamodump_path + "/dumps"):
        os.makedirs(dynamodump_path + "/dumps")

    if not os.path.exists(holserverdata_path):
        os.makedirs(holserverdata_path)

    if not os.path.exists(holserveruser_path):
        os.makedirs(holserveruser_path)

    if not os.path.exists(holserverdata_path + "/data"):
        os.makedirs(holserverdata_path + "/data")

    if not os.path.exists(holserveruser_path + "/data"):
        os.makedirs(holserveruser_path + "/data")


    return paths_set


def main(argv):
    if not verify_paths():
        exit()

    if (len(argv) == 2) and (argv[1] == "-list"):
        print("Available 'data' dumps: \n" + list_dumps(holserverdata_path) + "<end of list>")
        print("Available 'user' dumps: \n" + list_dumps(holserveruser_path) + "<end of list>")
        exit()

    elif len(argv) != 3:
        print("ERROR: No dump and/or player id specified! Usage: " + argv[0] + " <date> <player_id>")
        print("e.g. " + argv[0] + " 2016-01-14_01")
        print("Do not specify the time value (e.g. 2016-01-14_01.00)")
        print("To get a list of dumps, use: " + argv[0] + " -list")
        exit()

    dump_date = argv[1]
    player_id = argv[2]

    dump_filename_data = get_dump(holserverdata_path, check_dump(holserverdata_path, dump_date))
    sanitize(holserverdata_path, dump_filename_data, player_id)

    dump_filename_user = get_dump(holserveruser_path, check_dump(holserveruser_path, dump_date))
    sanitize(holserveruser_path, dump_filename_user, player_id)

    do_docker_dynamodump(holserverdata_path)
    do_docker_dynamodump(holserveruser_path)


if __name__ == "__main__":
    dynamodump_path = os.path.expanduser(os.getenv('DYNAMODUMP_INSTALL_PATH'))
    holserverdata_path = dynamodump_path + "/holserver_game_data"
    holserveruser_path = dynamodump_path + "/holserver_user"
    main(sys.argv[0:])
