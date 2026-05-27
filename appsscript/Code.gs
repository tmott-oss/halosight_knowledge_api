// =============================================================================
// Halosight Knowledge — Google Workspace Add-on
// Searches the Halosight knowledge base from Gmail, Docs, and Sheets
// =============================================================================

var API_URL = "https://halosight-knowledge-api-691841119073.us-central1.run.app";

// API key is stored in Script Properties — never hardcode it here.
// To set it: Apps Script editor → Project Settings → Script Properties
// Add property: HALOSIGHT_API_KEY = your-key
var API_KEY = PropertiesService.getScriptProperties().getProperty("HALOSIGHT_API_KEY") || "";

// =============================================================================
// Entry points
// =============================================================================

function onHomepage(e) {
  return buildSidebar("");
}

function onGmailMessage(e) {
  return buildSidebar("");
}

// =============================================================================
// Search action — called when user submits a query
// =============================================================================

function onSearch(e) {
  var query = e.formInput.query;
  if (!query || query.trim() === "") {
    return buildSidebar("", "Please enter a question.");
  }
  var result = searchKnowledge(query.trim());
  return buildSidebar(query, "", result);
}

// =============================================================================
// API call
// =============================================================================

function searchKnowledge(query) {
  try {
    var response = UrlFetchApp.fetch(API_URL + "/ask", {
      method: "post",
      contentType: "application/json",
      headers: {
        "Authorization": "Bearer " + API_KEY
      },
      payload: JSON.stringify({
        question: query,
        top_k: 5
      }),
      muteHttpExceptions: true
    });

    var code = response.getResponseCode();
    if (code !== 200) {
      return "Error: API returned status " + code + ". Please try again.";
    }

    var data = JSON.parse(response.getContentText());
<<<<<<< HEAD
    return data.answer || "No answer returned.";
=======

    if (!data.answer) {
      return "No relevant content found for that question.";
    }

    return data.answer;
>>>>>>> 7ba2e84 (Add /ask endpoint with GPT-4o-mini synthesis)

  } catch (err) {
    return "Error connecting to Halosight Knowledge API: " + err.message;
  }
}

// =============================================================================
// UI builder
// =============================================================================

function buildSidebar(query, errorMsg, answer) {
  var builder = CardService.newCardBuilder()
    .setHeader(
      CardService.newCardHeader()
        .setTitle("Halosight Knowledge")
        .setSubtitle("Search your knowledge base")
    );

  // Search input section
  var inputSection = CardService.newCardSection();

  var queryInput = CardService.newTextInput()
    .setFieldName("query")
    .setTitle("Ask a question")
    .setHint("e.g. What is our ICP?")
    .setMultiline(false);

  if (query) {
    queryInput.setValue(query);
  }

  var searchButton = CardService.newTextButton()
    .setText("Search")
    .setOnClickAction(
      CardService.newAction().setFunctionName("onSearch")
    )
    .setTextButtonStyle(CardService.TextButtonStyle.FILLED);

  inputSection.addWidget(queryInput);
  inputSection.addWidget(searchButton);
  builder.addSection(inputSection);

  // Error message
  if (errorMsg) {
    var errorSection = CardService.newCardSection();
    errorSection.addWidget(
      CardService.newTextParagraph().setText("⚠️ " + errorMsg)
    );
    builder.addSection(errorSection);
  }

  // Answer section
  if (answer) {
    var answerSection = CardService.newCardSection()
      .setHeader("Answer");

    answerSection.addWidget(
      CardService.newTextParagraph().setText(answer)
    );

    builder.addSection(answerSection);
  }

  return builder.build();
}
