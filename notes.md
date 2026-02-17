Alcohol Label Verifier

  Design Decisions

  I started by pulling sample labels from the COLA database and spending a
  few hours in discussion with Claude Desktop before drafting the PRD and
  architecture. I decided on core must-have features that prove AI can handle
   visual processing of labels, then added should-have features for testing
  and rollout.

  A tool like this wouldn't be given full trust from the start, so I designed
   it around an Assist Mode: the AI extracts and compares, but a human agent
  makes the final call. The label appears on screen with bounding boxes
  marking where each requirement was met or missed. Department employees
  would grade the AI's work initially, slowly giving it more autonomy as
  confidence builds, but probably always spot-checking a sample every month,
   even at full deployment. I've left override and feedback buttons in the
  app to show what I'm thinking there.

  One question that came up during the PRD process: Claude warned that OCR
  can't reliably determine whether text is bold. The TTB requires certain
  text to be bold. If I could build a system that checks boldness at 80%
  accuracy versus one that skips it at 98% accuracy, would that tradeoff be
  worth sharing with the people who write the rules? I don't mean I'm
  planning to email them, but I'm curious how this initiative to roll out AI
  tools will influence the regulatory side.

  The architecture landed on: Python/FastAPI backend, Claude Sonnet for
  vision-based label extraction (best speed/quality tradeoff for the 5-second
   latency target), percentage-based bounding boxes from the LLM for visual
  markup, and a strategy-dispatch pattern where each label field is routed to
   the right comparison algorithm: exact match for government warnings,
  fuzzy for brand names and addresses, numeric with cross-validation for
  ABV/proof, presence-only for sulfites.

  Technical Challenges

  Matching edge cases. The LLM marks Holland and The Netherlands as a
  mismatch. I added them as synonyms for country-of-origin matching, but I
  know I can't catch every case like this. I'm imagining a scenario where a
  label lists two different "imported by" companies. That should fail, but
  wouldn't right now. A progressive rollout with heavy human oversight that
  backs off as these edge cases get caught seems like the right approach. It
  would be nice to have access to some failed applications representing the
  edge cases that actually come up.

  Class/type matching. My system was marking applications as failures when
  the class/type on the application didn't appear exactly on the label. But
  these were approved applications, so clearly something more nuanced is
  going on. Research showed there's a differentiation between administrative
  categories and text expected to match the bottle. Some products with enough
   "trade and consumer understanding" (like Southern Comfort) aren't
  required to print a composition statement at all. I wonder if there's a
  defined list and how products get on it. If there were, that logic would be
   straightforward to implement. Rather than writing regex that overfits to
  particular labels, I've left many class/type mismatches flagged as
  needs-review, which feels like the right call for a system that's meant to
  assist rather than replace human judgment.

  Accuracy. Early benchmarking with a free-tier LLM (Groq) hit about 60%
  accuracy. Switching to Anthropic's API brought a dramatic improvement for
  roughly 5 cents per test run. Model selection matters more than prompt
  engineering past a certain point.

  Image quality. Fine print is a recurring problem. I introduced image
  preprocessing for low-resolution labels, which helped. I think sending
  isolated sections of the label to the LLM, maybe extracting just the warning
  statement area, then enhancing the rest, would reduce those errors
  further. I didn't end up implementing this, but it's where I'd go next.

  Timing

  Adding re-extraction LLM calls for edge cases blew up response times. To
  get back under the 5-second target, I: reviewed which calls could use Haiku
   instead of Sonnet, parallelized calls that were running sequentially
  (brand extraction was accidentally sequential), reduced max image
  resolution, capped max tokens on initial extraction, and added thorough PDF
   extraction with regex before any LLM is invoked. That got
  single-application processing consistently under 5 seconds.

  Testing

  I burned down my original test suite when I realized I could grab single
  PDFs from the COLA database that contain both the application and label
  images. A single upload is more convenient and a better representation of
  how this tool would actually be used. I downloaded 25 applications and had
  Claude manipulate a few into applications that should fail, then built the
  test suite around three layers: accurate identification of application and
  labels within a PDF, accurate text extraction from label images, and
  accurate comparison of application data against extracted text.

  The final round of testing uses 59 applications downloaded from the COLA
  database. The system is in a good place. If I were rolling it out for real,
   I'd bias toward more needs-review flags and fewer auto-passes. The fields
   that need exact matches are solid, but the ones with nuance need real
  feedback over time to get right.
