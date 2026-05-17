"""
Moodle DOM selectors — centralised so a single theme change only touches this file.
Each selector is a tuple of candidates tried in order (first match wins).
"""

# ── Quiz attempt page ─────────────────────────────────────────────────────────

QUESTION_CONTAINER = (
    "div.que.multichoice",
    "div.que[class*='multichoice']",
    "div[id^='q'][class*='multichoice']",
)

QUESTION_TEXT = (
    "div.formulation .qtext",
    "div.formulation p",
    "div.qtext",
    "div.formulation",
    ".content .formulation",
)

ANSWER_ROW = (
    "div.answer div[class^='r']",
    "div.answer > div",
    ".ablock .answer > div",
)

RADIO_INPUT = "input[type='radio']"
RADIO_LABEL = "label"

# ── Navigation / hidden fields ────────────────────────────────────────────────

ATTEMPT_FORM           = "#responseform, form[action*='processattempt']"
HIDDEN_ATTEMPT_ID      = "input[name='attempt']"
HIDDEN_SESSKEY         = "input[name='sesskey']"
HIDDEN_THIS_PAGE       = "input[name='thispage']"
HIDDEN_NEXT_PAGE       = "input[name='nextpage']"
HIDDEN_SLOTS           = "input[name='slots']"
SUBMIT_NEXT            = "input[type='submit'][name='next'], .mod_quiz-next-nav, input[value*='próxima'], input[value*='Next']"
SUBMIT_FINISH          = "button:has-text('Enviar tudo e terminar'), button:has-text('Submit all and finish'), input[type='submit'][value*='Enviar tudo'], input[type='submit'][value*='Submit all']"
SUBMIT_FINISH_CONFIRM  = ".confirmation-buttons input.btn-primary, .confirmation-dialogue input[value*='Enviar'], .confirmation-buttons input[type='submit'], .confirmation-buttons input[type='button'], .yui3-widget-ft button, button:has-text('Sim'), button:has-text('OK'), button:has-text('Confirmar')"

# ── Quiz view page (before starting) ─────────────────────────────────────────

QUIZ_TITLE             = "h2.quiz-intro, h1, .page-header-headings h1"
START_ATTEMPT_BTN      = ".singlebutton button[type='submit'], .quizstartbuttondiv button, input[value*='Tentar'], input[value*='Attempt'], input[value*='Continue'], .singlebutton input[type='submit']"
QUIZ_INFO_TIME         = ".quizattemptcounts, .timelimit"

# ── Post-submission result ────────────────────────────────────────────────────

GRADE_STRING           = ".grade, .quizreviewsummary .grade, td.grade"
SCORE_FRACTION         = ".grade .fraction, .quizreviewsummary .fraction"
