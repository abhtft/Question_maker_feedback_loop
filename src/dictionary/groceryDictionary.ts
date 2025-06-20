interface DictionaryEntry {
  word: string;
  category: 'product' | 'brand' | 'unit' | 'quantity';
  confidence: number;
  alternatives?: string[];
}

interface CorrectionEntry {
  original: string;
  corrected: string;
  frequency: number;
  lastUsed: Date;
  context?: string[];
}

class GroceryDictionary {
  private products: Map<string, DictionaryEntry>;
  private units: Map<string, DictionaryEntry>;
  private corrections: Map<string, CorrectionEntry>;

  constructor() {
    this.products = new Map();
    this.units = new Map();
    this.corrections = new Map();
    this.initializeDictionaries();
  }

  private initializeDictionaries() {
    // Initialize with common grocery items
    const commonProducts = [
      'rice', 'wheat', 'flour', 'sugar', 'salt', 'oil', 'milk', 'eggs',
      'bread', 'butter', 'cheese', 'yogurt', 'fruits', 'vegetables',
      'potato', 'onion', 'tomato', 'apple', 'banana', 'orange'
    ];

    const commonUnits = [
      'kg', 'g', 'l', 'ml', 'pcs', 'packet', 'box', 'dozen'
    ];

    commonProducts.forEach(product => {
      this.products.set(product.toLowerCase(), {
        word: product,
        category: 'product',
        confidence: 0.9
      });
    });

    commonUnits.forEach(unit => {
      this.units.set(unit.toLowerCase(), {
        word: unit,
        category: 'unit',
        confidence: 0.9
      });
    });
  }

  public findCorrection(word: string): { 
    original: string;
    suggested: string;
    confidence: number;
  } | null {
    const lowerWord = word.toLowerCase();
    
    // Check corrections first
    const correction = this.corrections.get(lowerWord);
    if (correction) {
      return {
        original: word,
        suggested: correction.corrected,
        confidence: Math.min(0.9, 0.5 + (correction.frequency * 0.1))
      };
    }

    // Check products
    const product = this.products.get(lowerWord);
    if (product) {
      return null; // Word is already in dictionary with high confidence
    }

    // Find closest match in products
    let bestMatch = null;
    let highestConfidence = 0;

    for (const [dictWord, entry] of this.products.entries()) {
      const confidence = this.calculateSimilarity(lowerWord, dictWord);
      if (confidence > highestConfidence && confidence > 0.6) {
        highestConfidence = confidence;
        bestMatch = {
          original: word,
          suggested: entry.word,
          confidence: confidence
        };
      }
    }

    return bestMatch;
  }

  private calculateSimilarity(word1: string, word2: string): number {
    // Simple Levenshtein distance implementation
    const track = Array(word2.length + 1).fill(null).map(() =>
      Array(word1.length + 1).fill(null));
    
    for (let i = 0; i <= word1.length; i += 1) {
      track[0][i] = i;
    }
    for (let j = 0; j <= word2.length; j += 1) {
      track[j][0] = j;
    }

    for (let j = 1; j <= word2.length; j += 1) {
      for (let i = 1; i <= word1.length; i += 1) {
        const indicator = word1[i - 1] === word2[j - 1] ? 0 : 1;
        track[j][i] = Math.min(
          track[j][i - 1] + 1,
          track[j - 1][i] + 1,
          track[j - 1][i - 1] + indicator
        );
      }
    }

    const maxLength = Math.max(word1.length, word2.length);
    const distance = track[word2.length][word1.length];
    return 1 - (distance / maxLength);
  }

  public addCorrection(original: string, corrected: string) {
    const lowerOriginal = original.toLowerCase();
    const existing = this.corrections.get(lowerOriginal);

    if (existing) {
      existing.frequency++;
      existing.lastUsed = new Date();
      if (existing.corrected !== corrected) {
        // If correction changed, update it
        existing.corrected = corrected;
      }
    } else {
      this.corrections.set(lowerOriginal, {
        original: lowerOriginal,
        corrected,
        frequency: 1,
        lastUsed: new Date()
      });
    }

    // Save to localStorage
    this.saveCorrections();
  }

  private saveCorrections() {
    const correctionsArray = Array.from(this.corrections.entries());
    localStorage.setItem('groceryCorrections', JSON.stringify(correctionsArray));
  }

  public loadCorrections() {
    const saved = localStorage.getItem('groceryCorrections');
    if (saved) {
      const correctionsArray = JSON.parse(saved);
      this.corrections = new Map(correctionsArray);
    }
  }
}

export const groceryDictionary = new GroceryDictionary();
groceryDictionary.loadCorrections(); 