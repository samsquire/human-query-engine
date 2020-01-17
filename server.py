from flask import render_template
from flask import Flask
from flask import make_response, redirect, request
import os, smtplib, ssl, time
import yaml
import random
import re
import uuid
import hashlib
import collections
random.seed()
from random import randrange

app = Flask(__name__)

try:
    os.makedirs("/home/{}/secrets/tokens".format(os.environ["USER"]))
except FileExistsError as e:
    pass

def load_queries():
    return list(yaml.safe_load_all(open("queries.yml").read()))

def check_signed_in(from_cookie=False):
    email = None
    login = None
    username = ""
    if "email" in request.cookies:
        email = request.cookies["email"] 
    else:
        email = request.args.get('email')
    if "login" in request.cookies:
        login = request.cookies["login"] 
    else:
        login = request.args.get('login')
    signed_in = False
    user_email = None
    if login and email:
        # email = re.sub('[^0-9a-zA-Z]+', '', email)
        # login = re.sub('[^0-9a-zA-Z]+', '', login)
        token_path = "/home/{}/secrets/tokens/{}/{}".format(os.environ["USER"], email, login)
        if os.path.isfile(token_path):
            signed_in = True
            user_email, username = open(token_path).read().split(" ")
            
    return signed_in, username, user_email, email, login

@app.route('/')
def index():
    signed_in, username, user_email, email_token, login_token = check_signed_in()
    data = load_queries()
    questions = []

    for i in range(0, 25):
        query = randrange(len(data)) - 1
        query_data = data[query]["raise_query"]
        question = query_data["question"]
        pattern = re.compile(r"<([a-zA-Z]*)>") 
        definitions = []
        picked = collections.defaultdict(list)
        for substitution in pattern.findall(question):
            found_definition = None
            for definition in query_data["queries"]:
                if substitution == definition["name"]:  
                    found_definition = definition
            if found_definition:
                options = yaml.safe_load(open("data/{}.yml".format(found_definition["file"])).read())
                picked_option = randrange(len(options)) - 1
                while picked_option in picked[found_definition["file"]]:
                    picked_option = randrange(len(options)) - 1

                picked[found_definition["file"]].append(picked_option) 
                question = question.replace("<" + substitution + ">", options[picked_option])
                found_definition["value"] = options[picked_option]
                definitions.append(found_definition)

        generated_id = uuid.uuid1()
        open("/tmp/{}".format(generated_id), "w").write(yaml.dump({"question": question, "definitions": definitions }))

        question_id = data[query]["id"]
        questions.append({
            "question_id": question_id, 
            "question": question,
            "definitions": definitions, 
            "generated_id": generated_id,
            "responses": query_data.get("responses", [])
            })
    response = make_response(render_template('index.html', user_email=user_email, signed_in=signed_in, generated_id=generated_id, questions=questions))
    if email_token:
        response.set_cookie("email", email_token) 
    if login_token:
        response.set_cookie("login", login_token) 
    return response


@app.route('/submit', methods=["POST"])
def submit():
    signed_in, username, user_email, email_token, login_token = check_signed_in()
    user_data_path = "data/{}".format(username)
    question = request.form["question_id"]   
    found = False

    for query in load_queries():
        if query["id"] == question:
            found = True

    if not found:
        return redirect("/", code=302)
        
    try:
        os.makedirs(user_data_path)
    except FileExistsError as e:
        pass
    question_data = yaml.safe_load(open("/tmp/{}".format(request.form["generated_id"])).read())
    answer_file = os.path.join(user_data_path, "answers.yml")
    if os.path.isfile(answer_file):
        answer_data = yaml.safe_load(open(answer_file).read())
    else:
        answer_data = {"answers": []}

    answer_data["answers"].append({
                "question_id": question,
                "question": question_data,
                "selection": request.form.get("response", ""),
                "answer": request.form["answer"]})
    open(answer_file, "w").write(
            yaml.dump(answer_data, default_flow_style=False)
            )
     
    return redirect("/", code=302)

@app.route('/signin', methods=["POST"])
def signin():
    
    email = request.form["email"]   
    email_hashed = hashlib.sha256(email.encode('utf-8')).hexdigest()
    user = uuid.uuid1()
    token = uuid.uuid1()
    token_folder = "/home/{}/secrets/tokens/{}".format(os.environ["USER"], email_hashed)
    token_path = "/home/{}/secrets/tokens/{}/{}".format(os.environ["USER"], email_hashed, token)
    try:
        os.makedirs(token_folder)
    except FileExistsError as e:
        pass
    open(token_path, "w").write("{} {}".format(email, user))
    port = 465  # For SSL
    smtp_server = "smtp.gmail.com"
    sender_email = open("/home/{}/secrets/gmail-username".format(os.environ["USER"])).read()  # Enter your address
    receiver_email = email
    password = open("/home/{}/secrets/gmail-password".format(os.environ["USER"])).read()
    message = """\
Subject: Human Query Engine Signin link

http://localhost:5000/?email={}&login={}""".format(email_hashed, token, user)

    context = ssl.create_default_context()
    
    with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message)
    return render_template('signin.html')

     
if __name__ == "__main__":
    app.run(debug=True)
