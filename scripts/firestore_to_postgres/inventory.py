"""Read-only Firestore inventory for the 54-path mapping.

Does not write to Firestore. Prints counts and unexpected collections.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

KNOWN_TOP = {
    "users",
    "studentIntakes",
    "cohorts",
    "systemCache",
    "aiGenerationLogs",
    "aiQuestionFeedback",
    "aiEvalRuns",
}
KNOWN_COHORT_SUB = {
    "schedules",
    "seating",
    "attendances",
    "rollCalls",
    "notices",
    "scheduledNotices",
    "alertPopups",
    "posts",
    "qna",
    "materials",
    "assignments",
    "resumes",
    "mileageTransactions",
    "mileageSettings",
    "mileageProducts",
    "purchaseRequests",
    "mileageCart",
    "missionProgress",
    "weeklyTasks",
    "userProgress",
    "submissions",
    "assessments",
    "inflearnPackages",
    "studySources",
    "youtubeRecommendations",
    "projectTeams",
    "recommendationEvents",
    "curriculum",
    "curriculumSheets",
    "seatingRooms",
    "seatingAssignments",
    "seatingMeta",
    "formTasks",
    "vectorMetadata",
    "youtubeCurriculumCache",
    "studyNotes",
}
KNOWN_USER_SUB = {"todos", "alertPopupDismissals", "studyNotes"}
KNOWN_NESTED = {
    "comments",
    "messages",
    "submissions",
    "responses",
    "questions",
    "feedback",
    "revisions",
}

PATHS = [
    "users",
    "users/{uid}/todos",
    "users/{uid}/alertPopupDismissals",
    "users/{uid}/studyNotes",
    "studentIntakes",
    "cohorts",
    "cohorts/{c}/schedules",
    "…/curriculum/meta",
    "…/curriculumSheets",
    "…/materials",
    "…/attendances",
    "…/rollCalls",
    "…/seatingRooms",
    "…/seatingAssignments",
    "…/seatingMeta/default",
    "…/seating/{layout,assignment}",
    "…/projectTeams",
    "…/notices",
    "…/vectorMetadata/notices",
    "…/scheduledNotices",
    "…/alertPopups",
    "…/posts",
    "…/posts/{id}/comments",
    "…/qna",
    "…/qna/{id}/messages",
    "…/assignments",
    "…/assignments/{id}/submissions",
    "…/submissions",
    "…/weeklyTasks",
    "…/userProgress",
    "…/formTasks",
    "…/formTasks/{id}/responses",
    "…/assessments",
    "…/assessments/{id}/questions",
    "…/assessmentSubmissions",
    "…/mileageTransactions",
    "…/mileageSettings/config",
    "…/mileageProducts",
    "…/purchaseRequests",
    "…/mileageCart",
    "…/missionProgress",
    "…/resumes",
    "…/resumes/{id}/feedback",
    "…/resumes/{id}/revisions",
    "…/inflearnPackages",
    "…/youtubeRecommendations",
    "…/recommendationEvents",
    "…/youtubeCurriculumCache",
    "…/studySources",
    "…/studyNotes",
    "systemCache",
    "aiGenerationLogs",
    "aiQuestionFeedback",
    "aiEvalRuns",
]


def _init():
    cred_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(Path(__file__).resolve().parents[2] / "secrets" / "firebase-adminsdk.json"),
    )
    project = os.environ.get("FIREBASE_PROJECT_ID", "skn34-3rd-2team")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(cred_path),
            {"projectId": project},
        )
    return firestore.client()


def _keys(data: dict | None, n: int = 12) -> list[str]:
    if not data:
        return []
    return sorted(data.keys())[:n]


def _count(query) -> tuple[int, list[str]]:
    docs = list(query.stream())
    sample = []
    for doc in docs[:3]:
        sample.append({"id": doc.id, "keys": _keys(doc.to_dict())})
    return len(docs), sample


def main() -> int:
    db = _init()
    unexpected: list[str] = []
    inventory: dict[str, object] = {"paths": {}, "unexpected": [], "cohorts": []}

    top = [c.id for c in db.collections()]
    for name in top:
        if name not in KNOWN_TOP:
            unexpected.append(f"/{name}")

    def rec(path: str, n: int, sample=None):
        inventory["paths"][path] = {"count": n, "sample": sample or []}

    n, sample = _count(db.collection("users"))
    rec("users", n, sample)
    users = list(db.collection("users").stream())

    todos = dismissals = study_notes = 0
    for user in users:
        sub = [c.id for c in user.reference.collections()]
        for name in sub:
            if name not in KNOWN_USER_SUB:
                unexpected.append(f"users/{user.id}/{name}")
        t, _ = _count(user.reference.collection("todos"))
        todos += t
        d, _ = _count(user.reference.collection("alertPopupDismissals"))
        dismissals += d
        s, _ = _count(user.reference.collection("studyNotes"))
        study_notes += s
    rec("users/{uid}/todos", todos)
    rec("users/{uid}/alertPopupDismissals", dismissals)
    rec("users/{uid}/studyNotes", study_notes)

    n, sample = _count(db.collection("studentIntakes"))
    rec("studentIntakes", n, sample)
    n, sample = _count(db.collection("cohorts"))
    rec("cohorts", n, sample)

    totals = Counter()
    nested = Counter()
    cohorts = list(db.collection("cohorts").stream())
    inventory["cohorts"] = [c.id for c in cohorts]

    for cohort in cohorts:
        sub = [c.id for c in cohort.reference.collections()]
        for name in sub:
            if name not in KNOWN_COHORT_SUB:
                unexpected.append(f"cohorts/{cohort.id}/{name}")
            docs = list(cohort.reference.collection(name).stream())
            totals[name] += len(docs)
            if name == "posts":
                for post in docs:
                    for child in post.reference.collections():
                        if child.id not in KNOWN_NESTED:
                            unexpected.append(
                                f"cohorts/{cohort.id}/posts/{post.id}/{child.id}"
                            )
                        nested[f"posts/{child.id}"] += len(list(child.stream()))
            elif name == "qna":
                for thread in docs:
                    for child in thread.reference.collections():
                        if child.id not in KNOWN_NESTED:
                            unexpected.append(
                                f"cohorts/{cohort.id}/qna/{thread.id}/{child.id}"
                            )
                        nested[f"qna/{child.id}"] += len(list(child.stream()))
            elif name == "assignments":
                for item in docs:
                    for child in item.reference.collections():
                        if child.id not in KNOWN_NESTED:
                            unexpected.append(
                                f"cohorts/{cohort.id}/assignments/{item.id}/{child.id}"
                            )
                        nested[f"assignments/{child.id}"] += len(list(child.stream()))
            elif name == "formTasks":
                for item in docs:
                    for child in item.reference.collections():
                        if child.id not in KNOWN_NESTED:
                            unexpected.append(
                                f"cohorts/{cohort.id}/formTasks/{item.id}/{child.id}"
                            )
                        nested[f"formTasks/{child.id}"] += len(list(child.stream()))
            elif name == "assessments":
                for item in docs:
                    for child in item.reference.collections():
                        if child.id not in KNOWN_NESTED:
                            unexpected.append(
                                f"cohorts/{cohort.id}/assessments/{item.id}/{child.id}"
                            )
                        nested[f"assessments/{child.id}"] += len(list(child.stream()))
            elif name == "resumes":
                for item in docs:
                    for child in item.reference.collections():
                        if child.id not in KNOWN_NESTED:
                            unexpected.append(
                                f"cohorts/{cohort.id}/resumes/{item.id}/{child.id}"
                            )
                        nested[f"resumes/{child.id}"] += len(list(child.stream()))

    mapping = {
        "cohorts/{c}/schedules": "schedules",
        "…/curriculum/meta": "curriculum",
        "…/curriculumSheets": "curriculumSheets",
        "…/materials": "materials",
        "…/attendances": "attendances",
        "…/rollCalls": "rollCalls",
        "…/seatingRooms": "seatingRooms",
        "…/seatingAssignments": "seatingAssignments",
        "…/seatingMeta/default": "seatingMeta",
        "…/seating/{layout,assignment}": "seating",
        "…/projectTeams": "projectTeams",
        "…/notices": "notices",
        "…/vectorMetadata/notices": "vectorMetadata",
        "…/scheduledNotices": "scheduledNotices",
        "…/alertPopups": "alertPopups",
        "…/posts": "posts",
        "…/qna": "qna",
        "…/assignments": "assignments",
        "…/submissions": "submissions",
        "…/weeklyTasks": "weeklyTasks",
        "…/userProgress": "userProgress",
        "…/formTasks": "formTasks",
        "…/assessments": "assessments",
        "…/assessmentSubmissions": "assessmentSubmissions",
        "…/mileageTransactions": "mileageTransactions",
        "…/mileageSettings/config": "mileageSettings",
        "…/mileageProducts": "mileageProducts",
        "…/purchaseRequests": "purchaseRequests",
        "…/mileageCart": "mileageCart",
        "…/missionProgress": "missionProgress",
        "…/resumes": "resumes",
        "…/inflearnPackages": "inflearnPackages",
        "…/youtubeRecommendations": "youtubeRecommendations",
        "…/recommendationEvents": "recommendationEvents",
        "…/youtubeCurriculumCache": "youtubeCurriculumCache",
        "…/studySources": "studySources",
        "…/studyNotes": "studyNotes",
    }
    for path, col in mapping.items():
        rec(path, totals[col])
    rec("…/posts/{id}/comments", nested["posts/comments"])
    rec("…/qna/{id}/messages", nested["qna/messages"])
    rec("…/assignments/{id}/submissions", nested["assignments/submissions"])
    rec("…/formTasks/{id}/responses", nested["formTasks/responses"])
    rec("…/assessments/{id}/questions", nested["assessments/questions"])
    rec("…/resumes/{id}/feedback", nested["resumes/feedback"])
    rec("…/resumes/{id}/revisions", nested["resumes/revisions"])

    n, sample = _count(db.collection("systemCache"))
    rec("systemCache", n, sample)
    n, sample = _count(db.collection("aiGenerationLogs"))
    rec("aiGenerationLogs", n, sample)
    n, sample = _count(db.collection("aiQuestionFeedback"))
    rec("aiQuestionFeedback", n, sample)
    n, sample = _count(db.collection("aiEvalRuns"))
    rec("aiEvalRuns", n, sample)

    inventory["unexpected"] = sorted(set(unexpected))
    missing = [p for p in PATHS if p not in inventory["paths"]]
    inventory["missing_from_scan"] = missing

    out = Path(__file__).with_name("inventory.json")
    out.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(
        {
            "cohorts": inventory["cohorts"],
            "counts": {k: v["count"] for k, v in inventory["paths"].items()},
            "unexpected": inventory["unexpected"],
            "missing_from_scan": missing,
        },
        ensure_ascii=False,
        indent=2,
    ))
    if unexpected:
        print("UNMAPPED collections found — stop before DDL.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
