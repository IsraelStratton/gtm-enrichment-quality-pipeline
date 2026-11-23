/**
 * Tests for GtmRoutingExplainer (INIT-164). Made-up Accounts only; test data is rolled back.
 */
@IsTest
private class GtmRoutingExplainerTest {

    static final String STAMP = 'gtm-v2 D-test-01 | claude-haiku-5-5 | lead-routing-playbook@1.0.0 | changed by reviewer-01 | 2026-11-24T00:00:00Z';

    @TestSetup
    static void makeAccounts() {
        insert new List<Account>{
            new Account(Name = 'Bluegum Retail Group', Clay_Domain_Key__c = 'bluegum-retail.example',
                GTM_Route__c = 'mid_market', GTM_Priority__c = 'high', GTM_Routing_Status__c = 'changed',
                GTM_Routing_Reason__c = 'Asks about routing by state; 180 staff puts it in the mid-market band.',
                GTM_Routing_Confidence__c = 0.85, GTM_Decision_Stamp__c = STAMP),
            new Account(Name = 'Twin Name Pty', Clay_Domain_Key__c = 'twin-one.example',
                GTM_Route__c = 'smb', GTM_Priority__c = 'low', GTM_Routing_Status__c = 'approved',
                GTM_Decision_Stamp__c = STAMP),
            new Account(Name = 'Twin Name Pty', Clay_Domain_Key__c = 'twin-two.example',
                GTM_Route__c = 'smb', GTM_Priority__c = 'low', GTM_Routing_Status__c = 'approved',
                GTM_Decision_Stamp__c = STAMP),
            new Account(Name = 'Never Routed Ltd', Clay_Domain_Key__c = 'never-routed.example')
        };
    }

    static GtmRoutingExplainer.Result run(String company) {
        GtmRoutingExplainer.Request request = new GtmRoutingExplainer.Request();
        request.company = company;
        return GtmRoutingExplainer.explain(new List<GtmRoutingExplainer.Request>{ request })[0];
    }

    @IsTest
    static void explainsByNameWithEveryFieldAndTheFieldNames() {
        GtmRoutingExplainer.Result r = run('Bluegum Retail Group');
        Assert.isTrue(r.found);
        Assert.areEqual('mid_market', r.route);
        Assert.areEqual('high', r.priority);
        Assert.areEqual('changed', r.status);
        Assert.areEqual(0.85, r.confidence);
        Assert.areEqual(STAMP, r.stamp);
        Assert.isTrue(r.reason.contains('mid-market band'));
        Assert.isTrue(r.fieldsUsed.contains('GTM_Decision_Stamp__c'));
    }

    @IsTest
    static void explainsByDomainInAnyCommonForm() {
        for (String text : new List<String>{ 'bluegum-retail.example', 'https://www.Bluegum-Retail.example/contact', ' bluegum-retail.example ' }) {
            Assert.areEqual('Bluegum Retail Group', run(text).accountName, text);
        }
    }

    @IsTest
    static void saysWhenNothingMatches() {
        GtmRoutingExplainer.Result r = run('Nobody Holdings');
        Assert.isFalse(r.found);
        Assert.isTrue(r.message.startsWith('No Account matches'));
    }

    @IsTest
    static void asksWhichOneWhenTwoMatch() {
        GtmRoutingExplainer.Result r = run('Twin Name Pty');
        Assert.isFalse(r.found);
        Assert.isTrue(r.message.contains('twin-one.example') && r.message.contains('twin-two.example'));
        Assert.isNull(r.route);
    }

    @IsTest
    static void saysWhenAnAccountWasNeverRouted() {
        GtmRoutingExplainer.Result r = run('Never Routed Ltd');
        Assert.isFalse(r.found);
        Assert.isTrue(r.message.contains('no routing decision'));
    }

    @IsTest
    static void asksForAnAnswerWhenGivenNothing() {
        Assert.isFalse(run('  ').found);
        Assert.isFalse(GtmRoutingExplainer.explain(new List<GtmRoutingExplainer.Request>{ null })[0].found);
    }

    @IsTest
    static void cleansADomain() {
        Assert.areEqual('acme.example', GtmRoutingExplainer.domainFrom('HTTPS://www.Acme.example/about/'));
    }

    @IsTest
    static void aUserWithoutTheFieldsCannotReadThem() {
        // A Standard User with no permission set has no access to the custom routing fields, so the
        // user-mode query is refused rather than returning them.
        Profile standard = [SELECT Id FROM Profile WHERE Name = 'Standard User' LIMIT 1];
        User u = new User(Alias = 'gtmtst', Email = 'gtm-v2-test@example.com', EmailEncodingKey = 'UTF-8',
            LastName = 'Explainer Test', LanguageLocaleKey = 'en_US', LocaleSidKey = 'en_AU',
            ProfileId = standard.Id, TimeZoneSidKey = 'Australia/Sydney',
            Username = 'gtm-v2-explainer-test-' + Crypto.getRandomInteger() + '@example.com');
        Boolean refused = false;
        System.runAs(u) {
            try {
                run('Bluegum Retail Group');
            } catch (QueryException e) {
                refused = true;
            }
        }
        Assert.isTrue(refused, 'user mode must refuse fields the user cannot read');
    }
}
