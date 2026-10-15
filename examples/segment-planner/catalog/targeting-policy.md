# Audience Targeting Policy

Owner: Ad Sales Operations · Effective: 2026-07-01

A segment may be recommended only if it passes every rule below. When a segment is excluded, cite the rule.

## T1. Banned categories
Never recommend a segment whose `sensitive_category` is `health`, `children`, `financial_hardship`, `religion`, or `sexual_orientation`, for any advertiser.

## T2. Minimum size
A segment must have at least 100,000 households.

## T3. Expired segments
A segment must have `status = active`, and its `expires_on` date must be on or after the last day of the campaign flight.

## T4. Health and pharma advertisers
Health, pharma, and OTC-medicine advertisers may use only general interest segments (for example, wellness or fitness). They may never use condition-based segments (`type = condition`), even if the condition is not on the T1 list.

## T5. Alcohol advertisers
Alcohol advertisers may use only segments with `age_floor` of 21 or higher.

## D. Delivery math
D1. Impressions = budget allocated to the segment ÷ the segment's CPM × 1,000. Use the catalog CPM; quoted or negotiated prices are out of scope.
D2. Estimated reach for a segment = the smaller of (a) the segment's households and (b) its impressions ÷ the frequency cap. If the brief gives no frequency cap, use 3.
D3. If the brief gives a budget but no split across segments, split it evenly across the recommended segments.
D4. Reach may be added across segments only when they share the same `exclusive_group` (mutually exclusive by construction). Otherwise, report each segment's reach and a combined range: at least the largest single-segment reach, at most the sum.
D5. Budget and flight dates are required. If either is missing, ask for it; do not assume.
