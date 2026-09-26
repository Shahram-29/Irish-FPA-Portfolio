-- Net revenue retention by quarterly signup cohort: the cohort's MRR in each month since
-- signup, as a share of its MRR in the first month. Only months that every customer in the
-- cohort has reached are shown, so late-quarter signups don't distort the newest cohorts.
WITH signup AS (
    SELECT customer_id, MIN(month) AS signup_month FROM subscriptions GROUP BY customer_id
),
cohort_mrr AS (
    SELECT date_trunc('quarter', g.signup_month)          AS cohort,
           datediff('month', g.signup_month, s.month)     AS months_since_signup,
           SUM(s.mrr)                                     AS mrr
    FROM subscriptions s
    JOIN signup g USING (customer_id)
    GROUP BY ALL
)
SELECT cohort, months_since_signup,
       mrr / FIRST_VALUE(mrr) OVER (PARTITION BY cohort ORDER BY months_since_signup) AS retention
FROM cohort_mrr
QUALIFY cohort + INTERVAL (months_since_signup + 2) MONTH <= (SELECT MAX(month) FROM subscriptions)
ORDER BY cohort, months_since_signup
