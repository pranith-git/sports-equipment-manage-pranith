import datetime

def get_issue_id(student_id):
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{student_id}_{timestamp}"