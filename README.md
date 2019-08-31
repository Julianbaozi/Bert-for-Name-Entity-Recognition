# Bert-on-CVE

It augments CPE names into CVE description strings into product name and version ranges using BERT model.

https://github.com/google-research/bert

## bert model for tagging on CVE description
Set config.py, in bert_function change the path for data in read_data(), then run run.py.

Notes for the model (In the brackets are other methods I tried with worse performance)
1. Split the description into sentences to narrow down vector size.
2. Add sentence 'The product name is xx.' as the head of sentence. 
  (against adding nothing and adding both vendor name and product name)
3. Use substitute string 'X' to tag postfixes after WordPiece tokenization.
  (against using the same tag)
4. Ignore loss of head sentence, sustitutes and padded elements. Do the same when calculating all metrics.
  (against using them)
5. Use weight scheme log(max(f)/f)+mu, where f is the tag frequency and mu is hyperparameter.
  (against no weight or max(mu*log(sum(f)/f), 1) or (max(f)/f)^mu)
6. Use F-beta metric, where beta = 2 to stress on recall rate.

Best cross validation results are acc=97.8, F-bete=92.4, recall=95.2


## get versions from description
get_version() in get_version.py takes the word sequence and the tag sequence and will output a dictionary of {product name:[version range]}


## name matching
part of the codes are in name_mathing.ipyth
results and suggestions:

1. If '.js' is in cpe, then it is a javascript file. 
   If '.js' is in description, then it is a javascript file only when '.js' is not following a space.
2. The word that is followed by '.js' is well possible to be the original file name. For common words like 'video.js', combine other information like other cpes to decide.
3. For common library, 'jQuery' might be a good sign. But there are many jquery plugins that are not in npm.
3. Use tf-idf to find match coarsely, then match the original code (can be searched from cve) and the npm code (can be searched from npm coordinates)
4. because tf-idf is just a coarse matching, I will suggest only use product name or package name without the vendor name and the file path for npm.
