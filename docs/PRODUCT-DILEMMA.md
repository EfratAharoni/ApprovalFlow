# PRODUCT-DILEMMA.md — ApprovalFlow Autonomy Posture

## ההחלטה

אימצנו את ברירת המחדל של הפוליסה ללא שינוי:
- `AUTONOMY-CEILING`: $250
- `AUTONOMY-CONFIDENCE`: 0.80

## הצדקה

ניתוח sample-invoices.json מראה ש-$250 מאפשר אישור אוטומטי
של לפחות 4 נתיבים שונים (ארוחה, SaaS, נסיעה, חומרה קטנה)
מבלי לחשוף את הארגון לסיכון בלתי-מוצדק בשלב ההשקה.

| Fixture | סכום | קטגוריה | route |
|---|---|---|---|
| INV-1001 | $42 | meals | auto_approve |
| INV-1002 | $99 | saas | auto_approve |
| INV-1016 | $48 | travel | auto_approve |
| INV-1017 | $180 | hardware | auto_approve |

## מה הראוטר אוכף בפועל

הסכומים והכללים בקוד תואמים בדיוק לפוליסה §6.
שינוי הסף דורש עדכון של קובץ זה וה-Dapr config store —
ללא redeploy.

## תוכנית סקירה

נסקור את הסף לאחר 90 יום תפעול.
אם שיעור האישורים האוטומטיים נמוך מ-70% מסך הבקשות,
נשקול העלאה ל-$350 בכפוף לניתוח הנתונים האמיתיים.

---

# PRODUCT-DILEMMA.md — ApprovalFlow Autonomy Posture

## Decision

We adopted the policy defaults without modification:
- `AUTONOMY-CEILING`: $250
- `AUTONOMY-CONFIDENCE`: 0.80

## Justification

Analysis of sample-invoices.json shows that $250 allows automatic approval of at least
4 different paths (meal, SaaS, travel, small hardware) without exposing the organization
to unjustified risk at launch.

| Fixture | Amount | Category | Route |
|---|---|---|---|
| INV-1001 | $42 | meals | auto_approve |
| INV-1002 | $99 | saas | auto_approve |
| INV-1016 | $48 | travel | auto_approve |
| INV-1017 | $180 | hardware | auto_approve |

## What the Router Actually Enforces

The thresholds and rules in the code match policy §6 exactly.
Changing the threshold requires updating this file and the Dapr config store —
no redeploy required.

## Review Plan

We will review the threshold after 90 days of operation.
If the automatic approval rate falls below 70% of total requests,
we will consider raising it to $350, subject to analysis of real production data.
