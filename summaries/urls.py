from django.urls import path
from .views import *

app_name = 'summaries'

urlpatterns = [
    path("snapshot/", DetailProfileView.as_view(), name="detail-profile"),
    path("ledger-summary/", LedgerSummaryView.as_view(), name="ledger-summary"),
    path("has-snapshot/", HasSummarySnapshotView.as_view(), name="has-summary-snapshot"),
]