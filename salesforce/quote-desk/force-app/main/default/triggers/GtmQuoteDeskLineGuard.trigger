// GTM pipeline v2, chapter 5: the quote desk may read quote lines but never change them.
// Salesforce lets anyone who can edit a quote and see its price book create, edit and delete the
// quote's lines; the desk needs quote edit for the status and the two desk fields only. This trigger
// closes the rest for holders of the custom permission GTM_Quote_Desk_No_Line_Changes.
trigger GtmQuoteDeskLineGuard on QuoteLineItem (before insert, before update, before delete) {
    GtmQuoteDeskLineGuard.refuse(Trigger.isDelete ? Trigger.old : Trigger.new);
}
