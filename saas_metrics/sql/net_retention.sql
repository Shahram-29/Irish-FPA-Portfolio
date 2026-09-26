-- 12-month net and gross revenue retention: MRR now from customers who were paying 12 months
-- earlier, divided by what they paid then. Gross retention caps each customer at their earlier
-- MRR, so expansion from some customers can't hide churn from others.
SELECT cur.month,
       SUM(COALESCE(later.mrr, 0)) / SUM(base.mrr)                  AS nrr,
       SUM(LEAST(COALESCE(later.mrr, 0), base.mrr)) / SUM(base.mrr) AS grr
FROM subscriptions base
JOIN (SELECT DISTINCT month FROM subscriptions) cur ON cur.month = base.month + INTERVAL 12 MONTH
LEFT JOIN subscriptions later ON later.customer_id = base.customer_id AND later.month = cur.month
GROUP BY cur.month
ORDER BY cur.month
