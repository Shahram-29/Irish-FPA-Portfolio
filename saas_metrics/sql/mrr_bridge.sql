-- Monthly MRR bridge: opening + new + expansion + contraction + churn = closing.
WITH months AS (
    SELECT DISTINCT month FROM subscriptions
),
signup AS (
    SELECT customer_id, MIN(month) AS signup_month FROM subscriptions GROUP BY customer_id
),
-- One row per customer per month from signup onwards, with MRR 0 once they have left.
filled AS (
    SELECT g.customer_id, m.month, COALESCE(s.mrr, 0) AS mrr
    FROM signup g
    JOIN months m ON m.month >= g.signup_month
    LEFT JOIN subscriptions s ON s.customer_id = g.customer_id AND s.month = m.month
),
moves AS (
    SELECT customer_id, month, mrr,
           LAG(mrr, 1, 0) OVER (PARTITION BY customer_id ORDER BY month) AS prev_mrr
    FROM filled
)
SELECT month,
       SUM(prev_mrr)                                                               AS opening,
       SUM(CASE WHEN prev_mrr = 0 AND mrr > 0 THEN mrr ELSE 0 END)                 AS new,
       SUM(CASE WHEN prev_mrr > 0 AND mrr > prev_mrr THEN mrr - prev_mrr ELSE 0 END) AS expansion,
       SUM(CASE WHEN mrr > 0 AND mrr < prev_mrr THEN mrr - prev_mrr ELSE 0 END)      AS contraction,
       SUM(CASE WHEN prev_mrr > 0 AND mrr = 0 THEN -prev_mrr ELSE 0 END)           AS churn,
       SUM(mrr)                                                                    AS closing,
       COUNT(CASE WHEN prev_mrr > 0 THEN 1 END)                                    AS opening_customers,
       COUNT(CASE WHEN prev_mrr = 0 AND mrr > 0 THEN 1 END)                        AS new_customers,
       COUNT(CASE WHEN prev_mrr > 0 AND mrr = 0 THEN 1 END)                        AS churned_customers,
       COUNT(CASE WHEN mrr > 0 THEN 1 END)                                         AS closing_customers
FROM moves
GROUP BY month
ORDER BY month
