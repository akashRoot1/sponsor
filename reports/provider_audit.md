# Careers Provider Audit

Generated: 2026-06-09

## Summary

The project previously had 76 company entries using the generic `company_careers` scraper. This pass converted 31 high-priority entries to direct provider mappings and reduced generic entries to 45.

Current source mix:

| Source type | Company entries |
| --- | ---: |
| `company_careers` | 45 |
| `workday` | 15 |
| `greenhouse` | 8 |
| `phenom` | 7 |
| `successfactors` | 7 |
| `eightfold` | 6 |
| `amazon_jobs` | 4 |
| `oracle_hcm` | 3 |
| `ashby` | 2 |
| `lever` | 1 |
| `smartrecruiters` | 1 |
| `fallback_search` | 1 |
| `attrax` | 1 |

## Converted In This Pass

| Company | Provider | Notes |
| --- | --- | --- |
| Adobe | `phenom` | Public `/widgets` endpoint. |
| HubSpot | `greenhouse` | Board slug `hubspotjobs`. |
| Toast | `greenhouse` | Board slug `toast`. |
| Guidewire | `workday` | Workday CXS on `wd5.myworkdaysite.com`. |
| Squarespace | `greenhouse` | Board slug `squarespace`. |
| 2K Games | `greenhouse` | Board slug `2k`. |
| Accenture Limited | `workday` | Workday CXS tenant `accenture`, site `AccentureCareers`. |
| Accenture Global Solutions Limited | `workday` | Same Accenture tenant. |
| HCL Ireland Information Systems Limited | `successfactors` | Search rows on `careers.hcltech.com/search/`. |
| HCL Technologies Limited | `successfactors` | Same HCLTech search site. |
| EY | `successfactors` | Search rows on `careers.ey.com/search/`. |
| Red Hat | `workday` | Workday CXS tenant `redhat`, site `jobs`. |
| PayPal | `eightfold` | Provider identified; public API access is restricted, parser falls back to public page extraction. |
| Circle | `phenom` | Public `/widgets` endpoint. |
| JPMorgan Chase | `oracle_hcm` | Oracle HCM Candidate Experience site `CX_1001`. |
| Citi Europe | `eightfold` | Provider identified; public page extraction. |
| Citi N.A. | `eightfold` | Same Citi careers provider. |
| BNY | `eightfold` | Provider identified; endpoint may be restrictive. |
| AIB | `successfactors` | Search rows on `jobs.aib.ie/search/`. |
| Cisco | `phenom` | Public `/widgets` endpoint. |
| Kaseya | `greenhouse` | Board slug `kaseya`. |
| Cloudera | `workday` | Workday CXS tenant `cloudera`, site `External_Career`. |
| Oracle EMEA | `oracle_hcm` | Oracle HCM Candidate Experience site `CX_45001`. |
| Oracle Financial Services | `oracle_hcm` | Same Oracle HCM site. |
| Pfizer | `workday` | Workday CXS tenant `pfizer`, site `PfizerCareers`. |
| Abbott Ireland | `workday` | Workday CXS tenant `abbott`, site `abbottcareers`. |
| Abbott Diagnostics | `workday` | Same Abbott tenant. |
| Medtronic | `eightfold` | Provider identified; endpoint may be restrictive. |
| Stryker | `workday` | Workday CXS tenant `stryker`, site `StrykerCareers`. |
| Alexion / AstraZeneca | `eightfold` | Provider identified; public page extraction. |
| Gilead | `workday` | Workday CXS tenant `gilead`, site `gileadcareers`. |

## Remaining Generic Company Entries

These entries still use `company_careers` and should be audited in the next batch.

| Company | Legal/company entry | Careers URL |
| --- | --- | --- |
| Google | Google Ireland Limited | https://www.google.com/about/careers/applications/jobs/results/ |
| Microsoft | Microsoft Ireland Research Unlimited Company | https://jobs.careers.microsoft.com/global/en/search |
| Microsoft | Microsoft Ireland Operations Limited | https://jobs.careers.microsoft.com/global/en/search |
| Meta | Meta Platforms Ireland Limited | https://www.metacareers.com/jobs |
| TikTok | TikTok Technology Limited | https://careers.tiktok.com |
| Apple | Apple Distribution International Limited | https://jobs.apple.com |
| Apple | Apple Operations International Limited | https://jobs.apple.com |
| LinkedIn | LinkedIn Ireland Unlimited Company | https://www.linkedin.com/careers |
| ServiceNow | ServiceNow Ireland Limited | https://careers.servicenow.com |
| Zendesk | Zendesk International Limited | https://jobs.zendesk.com |
| TCS | Tata Consultancy Services Limited | https://www.tcs.com/careers |
| TCS | Tata Consultancy Services Ireland Limited | https://www.tcs.com/careers |
| Cognizant | Cognizant Technology Solutions Ireland Limited | https://careers.cognizant.com |
| Infosys | Infosys Limited | https://www.infosys.com/careers |
| Infosys BPM | Infosys BPM Limited | https://www.infosysbpm.com/careers |
| Capgemini | Capgemini Ireland Limited | https://www.capgemini.com/careers |
| Deloitte | Deloitte Ireland LLP | https://apply.deloitte.com/careers |
| KPMG | KPMG | https://kpmg.com/ie/en/home/careers.html |
| PwC | PricewaterhouseCoopers Services | https://www.pwc.ie/careers.html |
| IBM | IBM Global Services Limited | https://www.ibm.com/careers |
| IBM | IBM Ireland Limited | https://www.ibm.com/careers |
| NTT DATA | NTT DATA Services Ireland Limited | https://www.nttdata.com/global/en/careers |
| Expleo | Expleo Technology Ireland Limited | https://expleo.com/global/en/careers |
| GlobalLogic | GlobalLogic Software and Technology Ireland Limited | https://www.globallogic.com/careers |
| Liberty IT | Liberty Information Technology Limited | https://www.liberty-it.co.uk/careers |
| General Motors | General Motors IT Services Ireland Ltd | https://search-careers.gm.com |
| Fenergo | Fenergo Limited | https://www.fenergo.com/careers |
| Bank of America | Bank of America Europe Designated Activity Company | https://careers.bankofamerica.com |
| Bank of Ireland | Bank of Ireland Group PLC | https://careers.bankofireland.com |
| Permanent TSB | Permanent TSB Public Limited Company | https://www.ptsb.ie/careers |
| ICE | ICE Data Services Ireland Limited | https://www.ice.com/careers |
| Bloomberg | Bloomberg Data Management Services Limited | https://www.bloomberg.com/company/careers |
| Intel | Intel Ireland Limited | https://jobs.intel.com |
| Intel | Intel Research and Development Ireland Limited | https://jobs.intel.com |
| Dell | Dell Products Unlimited Company | https://jobs.dell.com |
| Dell EMC | EMC Information Systems International Unlimited Company | https://jobs.dell.com |
| Arista | Arista Technology Ireland Unlimited Company | https://www.arista.com/en/careers |
| Huawei | Huawei Technologies Ireland Co Ltd | https://career.huawei.com |
| Infineon | Infineon Technologies Semiconductor Ireland Limited | https://www.infineon.com/careers |
| Logitech | Logitech Ireland Services Limited | https://jobs.jobvite.com/logitech |
| McKesson | McKesson Cork Business Solutions Unlimited Company | https://careers.mckesson.com |
| Optum | Optum Services Ireland Limited | https://careers.unitedhealthgroup.com |
| WuXi Biologics | WuXi Biologics Ireland Limited | https://www.wuxibiologics.com/careers |
| Johnson & Johnson | Johnson & Johnson Vision Care Ireland Unlimited Company | https://www.careers.jnj.com |
| Regeneron | Regeneron Ireland DAC | https://careers.regeneron.com |

## Next Batch Candidates

Recommended next targets: Google, Microsoft, Meta, Apple, TikTok, ServiceNow, Zendesk, Cognizant, Deloitte, IBM, Bank of America, Intel, Dell, Optum, Johnson & Johnson, Regeneron.

Several of these use custom APIs or restricted front ends rather than the common providers already implemented, so they should be handled with dedicated parsers only after their public endpoints are verified.
