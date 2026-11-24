// Tests for GtmQuoteDeskLineGuard: a holder of the desk's permission set can create, change or
// delete no quote line; everyone else is not affected; the desk can still change the quote itself.
@IsTest
private class GtmQuoteDeskLineGuardTest {
    @TestSetup
    static void data() {
        Product2 product = new Product2(Name = 'Guard test seat', ProductCode = 'GUARD-TEST', IsActive = true);
        insert product;
        PricebookEntry entry = new PricebookEntry(Pricebook2Id = Test.getStandardPricebookId(), Product2Id = product.Id, UnitPrice = 600, IsActive = true);
        insert entry;
        Account account = new Account(Name = 'Guard Test Pty Ltd');
        insert account;
        Opportunity opp = new Opportunity(Name = 'Guard test', AccountId = account.Id, StageName = 'Proposal/Price Quote',
                                          CloseDate = Date.today().addDays(30), Pricebook2Id = Test.getStandardPricebookId());
        insert opp;
        Quote quote = new Quote(Name = 'Guard test quote', OpportunityId = opp.Id, Pricebook2Id = Test.getStandardPricebookId(), Status = 'Needs Review');
        insert quote;
        insert new QuoteLineItem(QuoteId = quote.Id, PricebookEntryId = entry.Id, Quantity = 10, UnitPrice = 600);
    }

    static User deskUser() {
        User u;
        System.runAs(new User(Id = UserInfo.getUserId())) {
            Profile p = [SELECT Id FROM Profile WHERE Name = 'Minimum Access - Salesforce' LIMIT 1];
            String tail = String.valueOf(Math.abs(Crypto.getRandomInteger()));
            u = new User(FirstName = 'Guard', LastName = 'Test', Alias = 'gtest', Email = 'guard.test@example.com',
                         Username = 'gtm-v2-guard-test-' + tail + '@example.com', ProfileId = p.Id, TimeZoneSidKey = 'Australia/Sydney',
                         LocaleSidKey = 'en_AU', EmailEncodingKey = 'UTF-8', LanguageLocaleKey = 'en_US');
            insert u;
            PermissionSet ps = [SELECT Id FROM PermissionSet WHERE Name = 'GTM_v2_Quote_Desk' LIMIT 1];
            insert new PermissionSetAssignment(AssigneeId = u.Id, PermissionSetId = ps.Id);
        }
        return u;
    }

    static void expectRefused(String what, DmlException e) {
        System.assert(e.getMessage().contains(GtmQuoteDeskLineGuard.MESSAGE), what + ': ' + e.getMessage());
    }

    @IsTest
    static void theDeskCannotChangeCreateOrDeleteALine() {
        User desk = deskUser();
        QuoteLineItem line = [SELECT Id, QuoteId, PricebookEntryId, Quantity FROM QuoteLineItem LIMIT 1];
        System.runAs(desk) {
            System.assert(FeatureManagement.checkPermission(GtmQuoteDeskLineGuard.PERMISSION), 'the desk holds the custom permission');
            try {
                update new QuoteLineItem(Id = line.Id, Quantity = 999);
                System.assert(false, 'an edit was allowed');
            } catch (DmlException e) {
                expectRefused('edit', e);
            }
            try {
                insert new QuoteLineItem(QuoteId = line.QuoteId, PricebookEntryId = line.PricebookEntryId, Quantity = 1, UnitPrice = 1);
                System.assert(false, 'a new line was allowed');
            } catch (DmlException e) {
                expectRefused('create', e);
            }
            try {
                delete new QuoteLineItem(Id = line.Id);
                System.assert(false, 'a delete was allowed');
            } catch (DmlException e) {
                expectRefused('delete', e);
            }
            update new Quote(Id = line.QuoteId, Status = 'Approved');
        }
        QuoteLineItem after = [SELECT Quantity FROM QuoteLineItem WHERE Id = :line.Id];
        System.assertEquals(10, after.Quantity, 'the line is unchanged');
        System.assertEquals(1, [SELECT COUNT() FROM QuoteLineItem], 'no line was added or removed');
        System.assertEquals('Approved', [SELECT Status FROM Quote WHERE Id = :line.QuoteId].Status, 'the desk can still decide the quote');
    }

    @IsTest
    static void everyoneElseIsNotAffected() {
        QuoteLineItem line = [SELECT Id FROM QuoteLineItem LIMIT 1];
        System.assert(!FeatureManagement.checkPermission(GtmQuoteDeskLineGuard.PERMISSION), 'the test admin does not hold the permission');
        update new QuoteLineItem(Id = line.Id, Quantity = 12);
        System.assertEquals(12, [SELECT Quantity FROM QuoteLineItem WHERE Id = :line.Id].Quantity);
        delete new QuoteLineItem(Id = line.Id);
        System.assertEquals(0, [SELECT COUNT() FROM QuoteLineItem]);
    }
}
