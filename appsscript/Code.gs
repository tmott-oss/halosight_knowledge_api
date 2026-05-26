// =============================================================================
// Halosight Knowledge — Google Workspace Add-on
// Searches the Halosight knowledge base from Gmail, Docs, and Sheets
// =============================================================================

var API_URL = "https://halosight-knowledge-api-691841119073.us-central1.run.app";
var API_KEY = "hk_FGYgWe6C2dRK441qTqmiWmi_kwjKQujjNP--qIFLyfU";

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
    var response = UrlFetchApp.fetch(API_URL + "/search", {
      method: "post",
      contentType: "application/json",
      headers: {
        "Authorization": "Bearer " + API_KEY
      },
      payload: JSON.stringify({
        query: query,
        top_k: 5
      }),
      muteHttpExceptions: true
    });

    var code = response.getResponseCode();
    if (code !== 200) {
      return "Error: API returned status " + code + ". Please try again.";
    }

    var data = JSON.parse(response.getContentText());
    var results = data.results || [];

    if (results.length === 0) {
      return "No relevant content found for that question.";
    }

    // Combine the top results into a single readable answer
    var answer = results.map(function(r) {
      return r.content;
    }).join("\n\n---\n\n");

    return answer;

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
