# Matriser [0:00]

Sjätte föreläsningen i linjär algebra. Den går igenom hur man räknar med matriser, vilka räkneregler som gäller och vad matriser används till. Matrisinvers hann föreläsaren inte med.

## Grundbegrepp [0:43]

En m gånger n-matris är en rektangulär tabell med reella tal, med m rader och n kolonner.

### Storlek [0:51]

Storleken anges alltid som antal rader först och antal kolonner sedan. En matris med två rader och fyra kolonner är en 2 gånger 4-matris.

### Kvadratiska matriser och kolonnmatriser [1:36]

En matris med lika många rader som kolonner kallas kvadratisk. En n gånger 1-matris kallas kolonnmatris och används för att skriva vektorer i R^n.

### Positioner och index [2:07]

Positionerna räknas från övre vänstra hörnet, rad först och kolonn sedan. a₂₃ är talet på rad 2, kolonn 3.

### Matriser via formel [3:01]

Man kan ange en matris med en formel för talet på position i, j. Matrisen med (-1)^(i+j) på varje position växlar tecken längs rader och kolonner. Formeln säger inte storleken, så den måste anges separat.

### Diagonalmatriser [5:00]

Diagonalen i en kvadratisk matris är positionerna 1,1, 2,2 och så vidare. En diagonalmatris har bara nollor utanför diagonalen, men på diagonalen får det också stå nollor.

## Räkneoperationer [6:29]

Matriser kan multipliceras med tal, adderas och multipliceras med varandra.

### Multiplikation med tal [6:37]

Varje position multipliceras med talet. Minus A betyder -1 gånger A, så alla tecken byts.

### Addition [7:39]

Två matriser av samma storlek adderas position för position. Har de olika storlek är summan odefinierad.

### När produkten finns [8:55]

AB är definierad bara om A har lika många kolonner som B har rader. En m gånger p-matris gånger en p gånger n-matris ger en m gånger n-matris.

### Rad gånger kolonn [11:31]

En radmatris gånger en kolonnmatris av samma längd ger en 1 gånger 1-matris. Talet är skalärprodukten, första gånger första plus andra gånger andra och så vidare.

### Allmän matrisprodukt [13:33]

Talet på position i, j i AB är rad i i A gånger kolonn j i B. Varje position kräver alltså en egen skalärprodukt.

### Räkneexempel [15:22]

Föreläsaren multiplicerar 2 gånger 2-matriser, en kvadratisk matris med en kolonn och en 3 gånger 2-matris med en 2 gånger 2-matris. Ett exempel där storlekarna inte passar visar att produkten då inte går att räkna ut.

### Uppställningstricket [22:38]

Man kan skriva den högra matrisen ovanför resultatet och den vänstra till vänster om det. Det hjälper i början, men blir rörigt när man multiplicerar flera matriser i följd.

## Räkneregler [27:24]

De flesta räkneregler fungerar som för tal. Undantaget är att ordningen i en produkt spelar roll.

### Associativitet och distributivitet [28:11]

(AB)C är lika med A(BC), så parenteser behövs inte. A(B + C) är AB + AC, och A måste stå till vänster i båda termerna.

### Bryt ut bråk [29:21]

Ett tal kan brytas ut ur en matrisprodukt. Föreläsaren bryter ut en halv ur en matris med bråk, multiplicerar heltalsmatriserna och låter svaret stå som ett halv gånger en matris.

### AB är inte BA [34:29]

Matrismultiplikation är inte kommutativ. En 1 gånger 3-matris gånger en 3 gånger 1-matris ger en 1 gånger 1-matris, men i omvänd ordning blir det en 3 gånger 3-matris. Två matriser kommuterar om AB råkar vara lika med BA.

## Särskilda matriser [39:31]

Nollmatrisen och identitetsmatrisen beter sig som talen 0 och 1.

### Nollmatrisen [39:31]

Nollmatrisen har nollor överallt och finns i varje storlek. A + 0 är A, och A gånger nollmatrisen är nollmatrisen.

### Identitetsmatrisen [41:43]

Identitetsmatrisen I är en kvadratisk diagonalmatris med ettor på diagonalen. IA och AI är båda lika med A.

## Uppgifter [47:36]

Föreläsaren räknar flera uppgifter som övar räknereglerna.

### Uttryck med identitetsmatris [47:36]

När storleken på I inte anges väljer man den storlek som gör uttrycket definierat. Här blir I en 2 gånger 2-matris.

### Matrisekvationer [50:32]

Ekvationen 3A - 2X = B löses först algebraiskt, som om bokstäverna vore tal. Sedan sätter man in matriserna och får X = ½(3A - B).

### Potenser [54:37]

A^k är A multiplicerad med sig själv k gånger, och A^0 definieras som identitetsmatrisen. Då gäller A^m A^n = A^(m+n) även när en exponent är noll.

### Nilpotent matris [56:12]

För matrisen N i uppgiften blir N² nästan bara nollor och N³ nollmatrisen. En matris där någon potens blir noll kallas nilpotent.

### Konjugatregeln [1:00:36]

(A + B)(A - B) blir A² - B² - AB + BA. Det är A² - B² bara om A och B kommuterar.

## Transponat [1:04:04]

Transponatet Aᵀ får man genom att låta rader bli kolonner. En m gånger n-matris får ett n gånger m-transponat.

### Räkneregler för transponat [1:05:43]

Transponatet av en summa är summan av transponaten. (AB)ᵀ är BᵀAᵀ, med ordningen omvänd, och (Aᵀ)ᵀ är A.

### Transponat av en produkt [1:07:15]

(ABC)ᵀ förenklas till CᵀBᵀAᵀ. Ordningen vänds helt.

### Symmetriska matriser [1:09:11]

En symmetrisk matris är sitt eget transponat, så den speglas i diagonalen. En skevsymmetrisk matris har Aᵀ = -A och därför nollor på diagonalen.

### Symmetrisk plus skevsymmetrisk [1:10:33]

A + Aᵀ är alltid symmetrisk och A - Aᵀ skevsymmetrisk. Därför kan varje kvadratisk matris skrivas som ½(A + Aᵀ) + ½(A - Aᵀ).

## Ekvationssystem som matriser [1:19:31]

Varje linjärt ekvationssystem kan skrivas som AX = Y, med koefficientmatrisen A, variabelkolonnen X och högerledet Y.

### Matrisformen AX = Y [1:19:41]

A är en m gånger n-matris, X en n gånger 1-matris och Y en m gånger 1-matris. Koefficienterna läses av i samma ordning som variablerna.

### Homogena system [1:21:52]

Systemet är homogent om Y är nollkolonnen, annars inhomogent.

### Linjärkombination av kolonner [1:22:12]

AX är x gånger första kolonnen plus y gånger andra kolonnen och så vidare. Geometriskt går man x, y och z steg längs kolonnvektorerna.

### Blockmatriser [1:23:33]

En stor matris kan skrivas med mindre matriser som block. Föreläsaren räknar ut kvadraten på en 4 gånger 4-matris genom att multiplicera 2 gånger 2-block i stället för att räkna 16 positioner.

### Kolonner som block [1:27:56]

Delar man upp A i kolonner blir BA matrisen med kolonnerna B gånger varje kolonn i A.

### Huvudsatsen [1:29:50]

För en kvadratisk matris A är tre villkor ekvivalenta. Kolonnerna är en bas i R^n, AX = 0 har bara lösningen X = 0, och AX = Y är lösbart för varje Y.

## Tillämpningar [1:32:10]

Matriser används långt utanför ekvationssystem.

### Grannmatriser för grafer [1:32:58]

Grannmatrisen har en etta på position i, j om det går en kant mellan nod i och nod j. Talet på position i, j i A^k är antalet vandringar av längd k från i till j.

### Good Will Hunting-grafen [1:35:04]

Föreläsaren räknar vandringar av längd 3 i grafen från filmen Good Will Hunting. Att multiplicera matriser är enklare än att räkna vägar för hand.

### Handelsresandeproblemet [1:37:57]

I en viktad graf anger varje tal kostnaden eller tiden mellan två städer. Att hitta snabbaste vägen genom alla städer är ett klassiskt svårt problem.

### Google-matrisen [1:38:42]

Google rankar webbsidor med en enorm matris över länkar mellan sidor. Bakgrunden i föreläsningssalen är ett utsnitt av motsvarande matris för Wikipedia.

### Relationsmatriser och släktträd [1:40:19]

Relationerna "är syster till" och "är mamma till" blir matriser med ettor och nollor. Deras produkt ger relationen "är moster till", och mammamatrisen i kvadrat ger "är mormor till".

### Korrelationsmatriser [1:43:14]

En korrelationsmatris visar hur starkt variabler som vikt, aktivitet och kaloriintag hänger ihop. Korrelation betyder inte att den ena orsakar den andra.

### Neurala nätverk [1:44:06]

Varje lager i ett neuralt nätverk är en matrismultiplikation med en viktmatris, följd av en icke-linjär del som nollställer negativa värden.

### Markovkedjor [1:45:21]

En övergångsmatris ger sannolikheten att gå från regn, moln eller sol en dag till varje väder nästa dag. Varje rad summerar till 1.
