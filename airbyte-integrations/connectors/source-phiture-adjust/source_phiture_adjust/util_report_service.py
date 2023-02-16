dimensions = [
    "day",
    "app",
    "app_token",
    "country_code",
    "country",
    "currency_code",
    "currency",
    "os_name",
    "campaign_id_network",
    "campaign_network",
    "adgroup_id_network",
    "adgroup_network",
    "creative_id_network",
    "creative_network",
    "network",
]

conversion_metrics_list = [
    "click_conversion_rate",
    "gdpr_forgets",
    "impression_conversion_rate",
    "limit_ad_tracking_installs",
    "limit_ad_tracking_install_rate",
    "limit_ad_tracking_reattribution_rate",
    "limit_ad_tracking_reattributions",
    "maus",
    "reattributions",
]

ad_spend_metrics_list = [
    "click_cost",
    "cost",
    "ecpc",
    "ecpi",
    "ecpm",
    "impression_cost",
    "install_cost",
    "paid_clicks",
    "paid_impressions",
    "paid_installs",
]

revenue_metrics_list = [
    "all_revenue",
    "cohort_ad_revenue",
    "cohort_all_revenue",
    "cohort_gross_profit",
    "cohort_revenue",
    "return_on_investment",
    "revenue_to_cost",
    "revenue",
    "revenue_est",
    "revenue_max",
    "revenue_min",
    "roas",
]

skad_metrics_list = [
    "conversion_value_total",
    "skad_conversion_value_gt_0",
    "skad_conversion_value_null",
    "skad_installs",
    "skad_qualifiers",
    "skad_reinstalls",
    "skad_total_installs",
    "invalid_payloads",
    "valid_conversions",
    "waus",
    "conversion_1",
    "conversion_2",
    "conversion_3",
    "conversion_4",
    "conversion_5",
    "conversion_6",
]

event_metrics = [
    "onboarding_completed",
    "purchase_maps",
    "purchase_premium",
    "sign_up",
    "sports_selected",
    "use_route",
]

event_metrics_suffix = [
    "events",
    "events_min",
    "events_max",
    "events_est",
    "revenue",
    "revenue_min",
    "revenue_max",
    "revenue_est",
]

event_metrics_list = [f"{metric}_{suffix}" for metric in event_metrics for suffix in event_metrics_suffix]
