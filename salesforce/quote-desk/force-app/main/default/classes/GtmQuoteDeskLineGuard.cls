// GTM pipeline v2, chapter 5: refuses any quote line change by a holder of the desk's custom permission.
// No DML, no callout, no email: it only marks the records the trigger hands it as errors.
public with sharing class GtmQuoteDeskLineGuard {
    public static final String PERMISSION = 'GTM_Quote_Desk_No_Line_Changes';
    public static final String MESSAGE = 'The GTM v2 quote desk may read quote lines but never create, change or delete them.';

    public static void refuse(List<QuoteLineItem> lines) {
        if (!FeatureManagement.checkPermission(PERMISSION)) {
            return;
        }
        for (QuoteLineItem line : lines) {
            line.addError(MESSAGE);
        }
    }
}
