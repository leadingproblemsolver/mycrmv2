import { NextRequest, NextResponse } from 'next/server';
import { upsertPlace } from '@/lib/db';
import { PlaceUpdate } from '@/lib/types';

export async function POST(req: NextRequest) {
  try {
    const updates: PlaceUpdate[] = await req.json();

    if (!Array.isArray(updates)) {
      return NextResponse.json({ error: 'Payload must be an array' }, { status: 400 });
    }

    let count = 0;
    // Loop and upsert directly into IndexedDB
    for (const update of updates) {
      // preferExisting=true ensures we don't overwrite Google Places data with Gemini nulls
      await upsertPlace(update, true); 
      count++;
    }

    return NextResponse.json({ 
      success: true, 
      merged: count 
    }, { status: 200 });

  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Failed to import' },
      { status: 500 }
    );
  }
}